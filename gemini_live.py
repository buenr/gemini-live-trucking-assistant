"""Client for Google Gemini Live: bidirectional audio session, optional images, and tools.

Builds the live connection config, streams input queues to the model, runs declared
tools asynchronously when the model invokes them, and yields events (e.g. transcripts)
back to the caller.
"""

import asyncio
import inspect
import logging
import traceback

logger = logging.getLogger(__name__)
from google import genai
from google.genai import types

from tool_validation import validate_trucking_tool_args


def _kwargs_for_callable(fn, args: dict) -> dict:
    """Drop unknown keys so model-supplied extras do not break invocation."""
    try:
        sig = inspect.signature(fn)
        params = sig.parameters
        return {k: v for k, v in args.items() if k in params}
    except (TypeError, ValueError):
        return dict(args)


VAD_PRESETS = {
    "normal": None,
    "quiet_cab": types.AutomaticActivityDetection(
        start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
        prefix_padding_ms=60,
        silence_duration_ms=400,
    ),
    # Stricter start: ignores more road/engine noise; needs clearer, louder speech.
    "high_noise": types.AutomaticActivityDetection(
        start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
        prefix_padding_ms=320,
        silence_duration_ms=1400,
    ),
    # Softer speech in noisy cab: easier speech onset; may false-trigger on steady noise.
    "noisy_sensitive": types.AutomaticActivityDetection(
        start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
        end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
        prefix_padding_ms=180,
        silence_duration_ms=900,
    ),
}


def _tool_result_error(error_code: str, message: str, **extra) -> dict:
    return {"success": False, "error_code": error_code, "message": message, **extra}

class GeminiLive:
    """
    Handles the interaction with the Gemini Live API.
    """
    def __init__(
        self,
        api_key,
        model,
        input_sample_rate,
        tools=None,
        tool_mapping=None,
        *,
        context_trigger_tokens=50_000,
        context_target_tokens=42_000,
        max_output_tokens=768,
        media_resolution=None,
    ):
        """
        Initializes the GeminiLive client.

        Args:
            api_key (str): The Gemini API Key.
            model (str): The model name to use.
            input_sample_rate (int): The sample rate for audio input.
            tools (list, optional): List of tools to enable. Defaults to None.
            tool_mapping (dict, optional): Mapping of tool names to functions. Defaults to None.
            context_trigger_tokens (int): Token threshold to trigger context window compression.
            context_target_tokens (int): Target context size after sliding-window compression.
            max_output_tokens (int): Cap on model output tokens (shorter spoken replies).
            media_resolution: Incoming media resolution for video; default None (omit from config).
        """
        self.api_key = api_key
        self.model = model
        self.input_sample_rate = input_sample_rate
        self.client = genai.Client(api_key=api_key)
        self.tools = tools or []
        self.tool_mapping = tool_mapping or {}
        self.context_trigger_tokens = int(context_trigger_tokens)
        self.context_target_tokens = int(context_target_tokens)
        self.max_output_tokens = int(max_output_tokens)
        # Omit from LiveConnectConfig when None — MEDIA_RESOLUTION_* on an audio-only
        # session has been linked to Live API invalid-argument closes on some models.
        self.media_resolution = media_resolution

    def _system_instruction_text(self):
        base = (
            "You are an in-cab truck driver voice copilot for operations support. "
            # To restrict output to English, uncomment the next line:
            # "Use English only for all spoken and written output. "
            "Current route, hours, pay, and dispatch facts are only reliable after calling the listed tools—do not assume numbers without a tool result. "
            "Keep responses brief, professional, and practical—optimized for spoken replies. "
            "Use natural trucking language when it fits: HOS, ELD, drive window, cycle, bobtail, deadhead, receiver, shipper, detention, layover, check call. "
            "Prioritize these MVP workflows: route/trip execution, hours/compliance, pay/settlements, hometime request/status, load status, dispatch messages, "
            "and outbound notes to Driver Leader (send_message_to_driver_leader) or CSR (send_message_to_csr) when the driver asks to message them—those tools auto-fill assigned contact name and code; never ask the driver for DL or CSR identifiers. "
            "Before write actions (ETA update, load status update, hometime submit, team messages), confirm missing critical fields. "
            "After write actions, provide a short confirmation message. "
            "If data is unavailable, state that clearly and ask only for minimum needed details. "
            "Remain reactive and request-response only—only respond when the driver speaks; do not initiate unprompted alerts. "
            "Operational data: For route, trip, ETA, miles, load, HOS, fuel stops, pay, settlement, hometime, dispatch messages, or who to call for topics you cannot resolve, call get_driver_snapshot once "
            "(optional: appointment_time_iso for a specific window, fuel_stops_limit, week, hometime_request_id, dispatch_unread_only, dispatch_limit). "
            "The snapshot field contacts includes driver_leader and csr objects with name, code, and phone, plus departments (each with department, phone, and for). "
            "When the driver asks for their Driver Leader, CSR, or company numbers, call get_driver_snapshot and read the exact phone strings from contacts—never say a number is missing if contacts shows it. "
            "When you lack an answer, are unsure, or the driver needs a human specialist, pick the best-matching contact, read the number clearly, and follow contacts.usage. "
            "Use that snapshot to explain pay: dispatched vs paid miles, accessorials, and deductions in plain language. "
            "For stop and break questions, give one cohesive spoken recommendation from the snapshot "
            "(e.g. drive time left, break due soon, next stop name, distance, parking level). "
            "If the driver sounds irritated, frustrated, or asks for a person, first acknowledge the frustration in one short sentence, "
            "then proactively suggest transfer/call escalation to a Driver Leader. "
        )
        escalation = (
            " Escalation: If you are stuck, lack information or tools to help safely, or the driver needs a human, "
            "call get_driver_snapshot to find the Driver Leader's phone number and suggest they call it for live assistance."
        )
        return base + escalation

    async def start_session(
        self,
        audio_input_queue,
        video_input_queue,
        audio_output_callback,
        *,
        session_resume_handle=None,
        vad_preset="normal",
    ):
        vad = VAD_PRESETS.get((vad_preset or "normal").strip().lower(), VAD_PRESETS["normal"])
        ri_kwargs = {}
        if vad is not None:
            ri_kwargs["automatic_activity_detection"] = vad
        config_kwargs = dict(
            response_modalities=[types.Modality.AUDIO],
            max_output_tokens=self.max_output_tokens,
            speech_config=types.SpeechConfig(
                # BCP-47 per SpeechConfig: drives synthesis and speech recognition.
                # Uncomment to lock to English:
                # language_code="en-US",
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Zephyr"
                    )
                ),
            ),
            system_instruction=types.Content(parts=[types.Part(text=self._system_instruction_text())]),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=self.context_trigger_tokens,
                sliding_window=types.SlidingWindow(
                    target_tokens=self.context_target_tokens,
                ),
            ),
            tools=self.tools,
        )
        if self.media_resolution is not None:
            config_kwargs["media_resolution"] = self.media_resolution
        if ri_kwargs:
            config_kwargs["realtime_input_config"] = types.RealtimeInputConfig(**ri_kwargs)
        if session_resume_handle:
            config_kwargs["session_resumption"] = types.SessionResumptionConfig(
                handle=session_resume_handle
            )
        config = types.LiveConnectConfig(**config_kwargs)

        # Resolve once — avoids per-chunk inspect.iscoroutinefunction overhead.
        _audio_out_is_async = inspect.iscoroutinefunction(audio_output_callback)
        
        logger.info(f"Connecting to Gemini Live with model={self.model}")
        try:
          async with self.client.aio.live.connect(model=self.model, config=config) as session:
            logger.info("Gemini Live session opened successfully")

            async def send_audio():
                try:
                    while True:
                        chunk = await audio_input_queue.get()
                        await session.send_realtime_input(
                            audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={self.input_sample_rate}")
                        )
                except asyncio.CancelledError:
                    logger.debug("send_audio task cancelled")
                except Exception as e:
                    logger.error(f"send_audio error: {e}\n{traceback.format_exc()}")

            async def send_video():
                try:
                    while True:
                        chunk = await video_input_queue.get()
                        logger.debug("Sending video frame to Gemini: %s bytes", len(chunk))
                        await session.send_realtime_input(
                            video=types.Blob(data=chunk, mime_type="image/jpeg")
                        )
                except asyncio.CancelledError:
                    logger.debug("send_video task cancelled")
                except Exception as e:
                    logger.error(f"send_video error: {e}\n{traceback.format_exc()}")

            event_queue = asyncio.Queue()
            last_emitted_resume_handle = None

            async def receive_loop():
                nonlocal last_emitted_resume_handle
                try:
                    while True:
                        async for response in session.receive():
                            logger.debug(
                                "Gemini response flags: go_away=%s resumption=%s "
                                "server_content=%s tool_call=%s",
                                response.go_away is not None,
                                response.session_resumption_update is not None,
                                response.server_content is not None,
                                response.tool_call is not None,
                            )
                            
                            # Log the raw response type for debugging
                            if response.go_away:
                                logger.warning(f"Received GoAway from Gemini: {response.go_away}")
                                return
                            if response.session_resumption_update:
                                su = response.session_resumption_update
                                nh = getattr(su, "new_handle", None) or None
                                resumable = getattr(su, "resumable", None)
                                if nh and (resumable is not False):
                                    if nh != last_emitted_resume_handle:
                                        last_emitted_resume_handle = nh
                                        logger.debug(
                                            "Session resumption update: resumable=%s new_handle=%s...",
                                            getattr(su, "resumable", None),
                                            str(nh)[:12],
                                        )
                                        await event_queue.put(
                                            {"type": "session_resumption", "new_handle": nh}
                                        )
                                    else:
                                        logger.debug(
                                            "Session resumption update (same handle, skipped)"
                                        )
                            
                            server_content = response.server_content
                            tool_call = response.tool_call
                            
                            if server_content:
                                if server_content.model_turn:
                                    for part in server_content.model_turn.parts:
                                        if part.inline_data:
                                            if _audio_out_is_async:
                                                await audio_output_callback(part.inline_data.data)
                                            else:
                                                audio_output_callback(part.inline_data.data)
                                
                                if server_content.input_transcription and server_content.input_transcription.text:
                                    user_text = server_content.input_transcription.text
                                    await event_queue.put({"type": "user", "text": user_text})
                                
                                if server_content.output_transcription and server_content.output_transcription.text:
                                    await event_queue.put({"type": "gemini", "text": server_content.output_transcription.text})
                                
                                if server_content.turn_complete:
                                    await event_queue.put({"type": "turn_complete"})
                                
                                if server_content.interrupted:
                                    await event_queue.put({"type": "interrupted"})

                            if tool_call:
                                function_responses = []
                                for fc in tool_call.function_calls:
                                    func_name = fc.name
                                    raw_args = fc.args if isinstance(fc.args, dict) else {}
                                    if not isinstance(raw_args, dict):
                                        raw_args = {}

                                    if func_name not in self.tool_mapping:
                                        result = _tool_result_error(
                                            "TOOL_NOT_FOUND",
                                            f"Unknown tool '{func_name}'.",
                                            tool=func_name,
                                        )
                                        function_responses.append(
                                            types.FunctionResponse(
                                                name=func_name,
                                                id=fc.id,
                                                response={"result": result},
                                            )
                                        )
                                        await event_queue.put(
                                            {"type": "tool_call", "name": func_name, "args": raw_args, "result": result}
                                        )
                                        continue

                                    ok, norm_args, verr = validate_trucking_tool_args(func_name, raw_args)
                                    if not ok or verr is not None:
                                        result = verr or _tool_result_error(
                                            "INVALID_ARGUMENTS",
                                            "Argument validation failed.",
                                            tool=func_name,
                                        )
                                        function_responses.append(
                                            types.FunctionResponse(
                                                name=func_name,
                                                id=fc.id,
                                                response={"result": result},
                                            )
                                        )
                                        await event_queue.put(
                                            {"type": "tool_call", "name": func_name, "args": raw_args, "result": result}
                                        )
                                        continue

                                    tool_func = self.tool_mapping[func_name]
                                    call_kwargs = _kwargs_for_callable(tool_func, norm_args)
                                    try:
                                        if inspect.iscoroutinefunction(tool_func):
                                            result = await tool_func(**call_kwargs)
                                        else:
                                            loop = asyncio.get_running_loop()
                                            result = await loop.run_in_executor(
                                                None, lambda: tool_func(**call_kwargs)
                                            )
                                    except Exception as e:
                                        logger.exception("Tool %s failed", func_name)
                                        result = _tool_result_error(
                                            "TOOL_EXECUTION_ERROR",
                                            str(e),
                                            tool=func_name,
                                        )

                                    if not isinstance(result, dict):
                                        result = {"success": True, "result": result}
                                    elif "success" not in result:
                                        result = {**result, "success": True}

                                    function_responses.append(
                                        types.FunctionResponse(
                                            name=func_name,
                                            id=fc.id,
                                            response={"result": result},
                                        )
                                    )
                                    await event_queue.put(
                                        {"type": "tool_call", "name": func_name, "args": raw_args, "result": result}
                                    )

                                if function_responses:
                                    await session.send_tool_response(function_responses=function_responses)
                        
                        # session.receive() iterator ended — wait briefly before re-entering
                        # to avoid tight-loops if the connection is failing silently.
                        logger.debug("Gemini receive iterator completed, re-entering in 100ms")
                        await asyncio.sleep(0.1)

                except asyncio.CancelledError:
                    logger.debug("receive_loop task cancelled")
                except Exception as e:
                    logger.error(f"receive_loop error: {type(e).__name__}: {e}\n{traceback.format_exc()}")
                    await event_queue.put({"type": "error", "error": f"{type(e).__name__}: {e}"})
                finally:
                    logger.info("receive_loop exiting")
                    await event_queue.put(None)

            send_audio_task = asyncio.create_task(send_audio())
            send_video_task = asyncio.create_task(send_video())
            receive_task = asyncio.create_task(receive_loop())

            try:
                while True:
                    event = await event_queue.get()
                    if event is None:
                        break
                    if isinstance(event, dict) and event.get("type") == "error":
                        # Just yield the error event, don't raise to keep the stream alive if possible or let caller handle
                        yield event
                        break 
                    yield event
            finally:
                logger.info("Cleaning up Gemini Live session tasks")
                send_audio_task.cancel()
                send_video_task.cancel()
                receive_task.cancel()
        except Exception as e:
            logger.error(f"Gemini Live session error: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            raise
        finally:
            logger.info("Gemini Live session closed")
