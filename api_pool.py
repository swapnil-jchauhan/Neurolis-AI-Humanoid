"""
Project Neurolis - Groq Multi-Key Fleet Pool Manager (api_pool.py)
------------------------------------------------------------------
Manages the 1 to 14 Groq API keys fleet pool:
- Robust multi-file loading (.env, env) from script dir and cwd
- Automatically creates .env if only env is present
- High-availability key failover, round-robin rotation, and quota recovery tracking
- Thread-safe retry wrapper with instant standby interrupt support
"""

import os
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import List, Optional, Set, Tuple

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False
    Groq = None

# ---------------- ENVIRONMENT & KEY LOADING ----------------
BASE_DIR = Path(__file__).resolve().parent
CWD = Path.cwd()

# 1. Sync 'env' to '.env' if needed so standard dotenv tools work
for target_dir in [BASE_DIR, CWD]:
    env_file = target_dir / "env"
    dot_env_file = target_dir / ".env"
    if env_file.exists() and not dot_env_file.exists():
        try:
            shutil.copyfile(env_file, dot_env_file)
        except Exception:
            pass

# 2. Load via python-dotenv if available
try:
    from dotenv import load_dotenv
    for target_dir in [CWD, BASE_DIR]:
        for fname in [".env", "env"]:
            p = target_dir / fname
            if p.exists():
                load_dotenv(p)
except ImportError:
    pass

# 3. Direct manual file parsing fallback to guarantee all 14 keys are loaded
for target_dir in [CWD, BASE_DIR]:
    for fname in [".env", "env"]:
        p = target_dir / fname
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("\"'")
                            if "#" in v:
                                v = v.split("#", 1)[0].strip().strip("\"'")
                            if k.startswith("GROQ_") and v:
                                os.environ[k] = v
            except Exception:
                pass

# 4. Collect up to 14 unique Groq API keys
GROQ_API_KEYS: List[str] = []
_candidates = [f"GROQ_API_KEY_{_i}" for _i in range(1, 15)] + ["GROQ_API_KEY", "GROQ_BACKUP_KEY"]
for _var in _candidates:
    _val = os.environ.get(_var, "").strip().strip("\"'")
    if _val and _val != "PASTE_YOUR_GROQ_KEY_HERE" and _val not in GROQ_API_KEYS:
        GROQ_API_KEYS.append(_val)
        if len(GROQ_API_KEYS) >= 14:
            break

# ---------------- CLIENT POOL INITIALIZATION ----------------
GROQ_PER_CALL_TIMEOUT = 4.0
GROQ_AUDIO_TIMEOUT = 7.0

groq_clients: List[any] = []
if HAS_GROQ:
    for _idx, _k in enumerate(GROQ_API_KEYS):
        try:
            groq_clients.append(Groq(api_key=_k, timeout=GROQ_PER_CALL_TIMEOUT, max_retries=0))
        except Exception as e:
            print(f"[Brain] Groq client #{_idx + 1} init notice: {e}")

_active_client_idx = 0
client = groq_clients[0] if groq_clients else None
resting_keys: Set[int] = set()

RATE_LIMIT_ERROR_PHRASE = "My backend services ran into an error, could you say that again?"

_standby_kill_event: Optional[threading.Event] = None


def set_standby_kill_event(event: threading.Event):
    """Binds the standby kill switch event so API retries can abort immediately on standby."""
    global _standby_kill_event
    _standby_kill_event = event


def get_active_client():
    """Returns the currently active Groq client instance."""
    global client, _active_client_idx
    if groq_clients:
        return groq_clients[_active_client_idx]
    return None


class GroqRateLimitExhausted(Exception):
    """Raised when tokens of current Groq key are exhausted and key has been rotated."""
    pass


def rotate_groq_key(reason: str = None, is_quota_exhausted: bool = False) -> int:
    """Rotates to the next Groq API key in the pool (1 -> 2 -> ... -> 14 -> 1). Only marks resting on true quota exhaustion."""
    global client, _active_client_idx, resting_keys
    if not groq_clients:
        return 0
    prev_idx = _active_client_idx
    if is_quota_exhausted:
        resting_keys.add(prev_idx)
    _active_client_idx = (_active_client_idx + 1) % len(groq_clients)
    client = groq_clients[_active_client_idx]
    for mod_name in ["listen", "__main__"]:
        if mod_name in sys.modules:
            try:
                mod = sys.modules[mod_name]
                if hasattr(mod, "groq_clients"):
                    mod.client = client
                    mod._active_client_idx = _active_client_idx
            except Exception:
                pass
    if reason:
        print(f"\n[Brain] Key #{prev_idx + 1} ({reason}). Swiftly rotated to Key #{_active_client_idx + 1} of {len(groq_clients)}.")
    elif is_quota_exhausted:
        print(f"\n[Brain] API quota reached on Key #{prev_idx + 1}. Swiftly rotated to Key #{_active_client_idx + 1} of {len(groq_clients)}.")
    else:
        print(f"\n[Brain] Key #{prev_idx + 1} failover rotated to Key #{_active_client_idx + 1} of {len(groq_clients)}.")
    return _active_client_idx


def _format_keys_list(nums: list) -> str:
    """Formats a list of 1-indexed key numbers into natural spoken English (e.g. 'Keys 2 through 5')."""
    if not nums:
        return ""
    if len(nums) == 1:
        return f"Key {nums[0]}"
    if len(nums) == 2:
        return f"Keys {nums[0]} and {nums[1]}"
    if nums == list(range(nums[0], nums[-1] + 1)):
        return f"Keys {nums[0]} through {nums[-1]}"
    return f"Keys {', '.join(str(n) for n in nums[:-1])} and {nums[-1]}"


def get_groq_fleet_status() -> Tuple[str, str]:
    """
    Returns (spoken_reply, console_text) describing the exact state of all 14 Groq key slots:
    - Active key
    - Standby keys
    - Resting keys (recovering rolling quota)
    - Unconfigured slots
    """
    global _active_client_idx, groq_clients, resting_keys
    total_slots = 14
    configured_count = len(groq_clients)
    if configured_count == 0:
        return (
            "No Groq API keys are currently configured in the environment.",
            "[Groq Fleet Monitor] No keys configured (Slots 1 through 14 are empty)."
        )

    active_num = _active_client_idx + 1
    resting_nums = sorted([idx + 1 for idx in resting_keys if idx != _active_client_idx and idx < configured_count])
    standby_nums = sorted([idx + 1 for idx in range(configured_count) if idx != _active_client_idx and idx not in resting_keys])
    unconfigured_nums = list(range(configured_count + 1, total_slots + 1))

    # Build spoken summary
    speech_parts = [f"I am currently running on Key {active_num}."]
    if resting_nums:
        verb = "is" if len(resting_nums) == 1 else "are"
        speech_parts.append(f"{_format_keys_list(resting_nums)} {verb} currently resting.")
    if standby_nums:
        verb = "is" if len(standby_nums) == 1 else "are"
        speech_parts.append(f"{_format_keys_list(standby_nums)} {verb} on standby.")
    elif not resting_nums:
        speech_parts.append("No backup keys are on standby.")

    if unconfigured_nums:
        speech_parts.append(f"{_format_keys_list(unconfigured_nums)} have not been configured.")
    else:
        speech_parts.append("All fourteen keys are fully configured.")

    spoken = " ".join(speech_parts)

    # Build formatted console display
    console_lines = ["\n======================= GROQ KEY FLEET STATUS ======================="]
    for slot in range(1, total_slots + 1):
        if slot == active_num:
            status = "ACTIVE (Handling requests)"
        elif (slot - 1) in resting_keys and slot <= configured_count:
            status = "RESTING (Exhausted rolling quota, recovering)"
        elif slot <= configured_count:
            status = "STANDBY (Ready in reserve)"
        else:
            status = "NOT CONFIGURED"
        console_lines.append(f"  Key {slot}: {status}")
    console_lines.append("=====================================================================\n")
    console_text = "\n".join(console_lines)

    return spoken, console_text


def handle_key_status_request() -> str:
    spoken, console_text = get_groq_fleet_status()
    print(console_text)
    return spoken


def is_key_status_inquiry(text: str) -> bool:
    """Detects whether user is inquiring about key status, active key, standby keys, or token quota."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(cleaned.split())

    # Conversational statement / non-inquiry exclusion guards:
    statement_exclusions = [
        "that means", "which means", "i meant", "we still have",
        "we have", "headroom", "token headroom", "because", "remember",
        "means that", "mean that", "yes i said"
    ]
    if any(ex in cleaned for ex in statement_exclusions):
        return False

    key_regexes = [
        r"\b(what|which)\s+key\s+(are\s+you\s+)?(running\s+on|on|using)\b",
        r"\bwhat\s+key\b",
        r"\bwhich\s+key\b",
        r"\bwhat\s+token\s+status\b",
        r"\b(check|tell|show|report|give)\s+(me\s+)?(the\s+)?(api\s+)?keys?\s*(status)?\b",
        r"\bkey\s+(status|stratus)\b",
        r"\btoken\s+(status|stratus|quota)\b",
        r"\b(how\s+many\s+)?(keys|tokens)\s+(left|remaining|active|standby)\b",
    ]
    if any(re.search(pat, cleaned) for pat in key_regexes):
        return True

    exact_triggers = [
        "key status", "keys status", "api status", "api key status", "check keys",
        "check api keys", "check key", "check the keys", "which key is active",
        "what key is active", "which key are you using", "what key are you using",
        "what key are you on", "which key are you on", "how many keys are active",
        "how many keys are configured", "how many keys are there", "how many keys do you have",
        "active key", "active keys", "standby keys", "token status", "tokens status",
        "how many tokens left", "how many tokens are left", "tokens left",
        "system status", "fleet status", "groq status", "status of keys", "status of api",
        "key stratus", "keys stratus", "api stratus",
        "tell me key status", "tell me the key status", "tell me api status", "tell me the api key status",
        "show key status", "show api status", "first tell me the key status",
        "what key are you running on", "which key are you running on",
        "know what key what token status"
    ]
    if any(t in cleaned for t in exact_triggers):
        return True

    # Combination matching:
    key_terms = {"key", "keys", "api", "token", "tokens"}
    status_terms = {"status", "stratus", "active", "standby", "configured", "left", "remaining", "check", "running"}
    query_indicators = {"what", "which", "how", "tell", "check", "show", "give", "report", "display", "status", "stratus"}
    if words.intersection(key_terms) and words.intersection(status_terms) and words.intersection(query_indicators):
        non_api_guards = {"life", "piano", "door", "car", "board", "keyboard"}
        if not words.intersection(non_api_guards):
            return True

    return False


def groq_call_with_retry(api_call_fn, *args, **kwargs):
    """
    Executes a Groq API call with automatic round-robin retry and failover across the key pool.
    - Set max_retries=0 on client to prevent SDK internal retry multiplication.
    - Fast failover: Max 2 attempts on network drop / timeout before failing fast.
    - Quota exhaustion (HTTP 429): Rotates through the pool.
    - Standby kill switch: Aborts immediately.
    """
    global client, _active_client_idx, resting_keys
    if not groq_clients:
        raise RuntimeError("Groq API client is not initialized. Please set a valid GROQ_API_KEY in your .env file.")

    qualname = getattr(api_call_fn, "__qualname__", "").lower()
    is_audio = "transcriptions" in qualname or "audio" in qualname

    # Round-robin through all available keys in the pool continuously
    max_key_attempts = max(len(groq_clients), 2)
    last_exception = None
    network_error_streak = 0

    for attempt in range(max_key_attempts):
        if _standby_kill_event is not None and _standby_kill_event.is_set():
            raise InterruptedError("Standby kill switch triggered.")
        active_c = groq_clients[_active_client_idx]
        target_fn = active_c.audio.transcriptions.create if is_audio else active_c.chat.completions.create

        req_kwargs = kwargs.copy()
        if "timeout" not in req_kwargs:
            req_kwargs["timeout"] = GROQ_AUDIO_TIMEOUT if is_audio else GROQ_PER_CALL_TIMEOUT

        try:
            res = target_fn(*args, **req_kwargs)
            if _active_client_idx in resting_keys:
                resting_keys.discard(_active_client_idx)
            return res
        except Exception as e:
            last_exception = e
            err_str = str(e).lower()

            # True quota exhaustion (HTTP 429 rate limit)
            if "429" in err_str or "rate limit" in err_str or "tokens per day" in err_str or "tpd" in err_str:
                network_error_streak = 0
                rotate_groq_key(reason="Daily quota exhausted (HTTP 429)", is_quota_exhausted=True)
            elif "timeout" in err_str or "timed out" in err_str or "connection" in err_str or "network" in err_str:
                network_error_streak += 1
                rotate_groq_key(reason="Network timeout / connection issue")
                if network_error_streak >= 2:
                    # Fail fast: internet connection is down or degraded; do not stall for 14 keys
                    break
            else:
                rotate_groq_key(reason=f"API error: {e}")

    if last_exception:
        raise last_exception
