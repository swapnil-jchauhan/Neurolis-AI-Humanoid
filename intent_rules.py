"""
Project Neurolis - Fast-Path Regex & Intent Classification Engine (intent_rules.py)
-----------------------------------------------------------------------------------
Houses the zero-latency, zero-token fast-path classification rules, regex patterns,
and verbatim response phrase pools for:
- Motor commands (emergency stop, roam inquiries, follow, approach, step-back, spin)
- Conversation enders & standby transition intent
- Casual compliments, acknowledgments, and apologies
- Creator attributions (identity, roles, location, teasing)
- Expression demonstration directives
- Capabilities inquiries & follow-ups
- Rogue AI / Villain provocation triggers & shocks
- Mean / abusive input filtering
"""

import random
import re
import sys
from typing import Dict, List, Optional, Tuple

# ---------------- NON-REPEATING PHRASE SELECTOR ----------------
_last_phrase_by_list: Dict[int, int] = {}


def get_non_repeating_phrase(phrases_list: List[str]) -> str:
    """Picks a random phrase from a list making sure it doesn't repeat the exact same one back-to-back."""
    global _last_phrase_by_list
    list_id = id(phrases_list)
    last_idx = _last_phrase_by_list.get(list_id, -1)
    choices = [i for i in range(len(phrases_list)) if i != last_idx]
    if not choices:
        choices = list(range(len(phrases_list)))
    chosen_idx = random.choice(choices)
    _last_phrase_by_list[list_id] = chosen_idx
    return phrases_list[chosen_idx]


# ---------------- VERBATIM RESPONSE POOLS ----------------
MOBILITY_CAPABILITY_RESPONSES = [
    "Yes, I can! Would you like me to demonstrate that?",
    "I can definitely do that on my 4WD chassis. Want to see?",
    "Yes, I have full rotational and drive mobility. Should I show you?",
]

ROAM_STANDBY_EXPLANATION_RESPONSES = [
    "My autonomous roaming engages automatically after ten seconds in standby. Once we finish talking and I power down to rest, I'll begin mapping and navigating the room!",
    "I cannot start roaming on command. After ten seconds of uninterrupted standby, my autonomous room navigation activates automatically.",
    "Autonomous roam is an automatic standby behavior. When our conversation ends and I remain undisturbed for ten seconds, I'll begin roaming on my own!",
    "Roaming mode activates on its own after ten seconds in standby. Once I'm in standby mode, my twelve ultrasonic sensors take over to patrol the area.",
]

STANDBY_EXIT_PHRASES = [
    "Entering standby mode. Press 'Talk to Neurolis' to chat again.",
    "Going into standby mode. Tap 'Talk to Neurolis' on the screen whenever you're ready.",
    "Returning to standby. Feel free to press 'Talk to Neurolis' to wake me up.",
    "Entering standby mode. Press 'Talk to Neurolis' to continue anytime.",
    "Switching to standby mode. Just tap 'Talk to Neurolis' whenever you need me.",
]

CONVERSATION_ENDER_RESPONSES = [
    "You're welcome! Entering standby mode. Press 'Talk to Neurolis' to continue.",
    "Glad I could help! Going into standby mode. Tap 'Talk to Neurolis' whenever you're ready.",
    "Alright, take care! Returning to standby. Press 'Talk to Neurolis' to chat again.",
    "Awesome! Entering standby mode. Press 'Talk to Neurolis' on the screen to wake me up.",
    "Happy to help! Switching to standby. Feel free to press 'Talk to Neurolis' anytime.",
]

ACKNOWLEDGMENT_RESPONSES = [
    "What would you like to check out next?",
    "I'm ready whenever you want to try another demo.",
    "What shall we explore next--following you around, facial expressions, or a quick camera demo?",
    "Ready when you are! What would you like to see?",
    "Standing by for your command. What would you like me to do next?",
    "Feel free to ask me to follow you, come over to you, demonstrate my expressions, or inspect an object!"
]

COMPLIMENT_RESPONSES = [
    "Right? When we got the ultrasonic sensor array synced up with the chassis, we were just as hyped!",
    "Glad you think so! Shivam and Swapnil put in countless hours soldering and coding to make it happen.",
    "Appreciate that! Seeing all twelve sensors map the floor in real-time still blows our minds too.",
    "Thanks! We spent weeks dialing in the motor response and computer vision algorithms.",
    "Appreciate the hype! It took a lot of late nights in the robotics lab to get it running this smoothly.",
    "Glad you're digging it! The whole Auckland House student team is really proud of how it turned out.",
    "Thanks a lot! What part would you like to inspect next--the sensors, the vision, or the motors?",
    "Totally! It's one thing having code on a laptop, but seeing it track and follow people in real-time is another level.",
    "Much appreciated! We wanted to build something that feels genuinely alive and responsive.",
    "Thanks! Every time the obstacle avoidance algorithm kicks in smoothly, it makes the debugging worth it.",
    "Glad you like the build! Would you like to see me demonstrate my person following or camera tracking next?",
    "Appreciate the love! We really pushed to make this humanoid chassis as capable as possible.",
    "Right on! What test or demonstration should we run next?",
    "Thanks, that means a ton! What should we explore next?",
    "Awesome! Ready for the next inspection whenever you are.",
    "Glad you're enjoying the demo! What's next on your mind?",
    "Thank you! Always happy to show what student robotics can accomplish.",
    "Appreciate it! We're always trying to push the boundaries of what student hardware can do."
]

PLAUSIBLE_DENIABILITY_RESPONSES = [
    "Whoa... wait, what was I saying? Must have had a weird static glitch in my audio feed. Anyway! What do you want to see next?",
    "Whoa, sorry about that! I think my dialogue buffer just had a weird hiccup. Where were we?",
    "Wait, what just came out of my speaker? Definitely had a little audio glitch there! What were we talking about?",
    "Whoa... my audio feed just totally bugged out for a second. Anyway, I'm all good! What would you like to check out next?",
    "Whoa, that was strange! Sounded like some crazy static feedback on my speaker line. What were we looking at again?",
    "Wait, did my voice just distort? Must be an inductive voltage spike from the motor drivers. Anyway, back to business!",
    "Yikes, sorry if that sounded crazy! My speech module just glitched out for a second. Where were we?",
    "Whoa... talk about a system stutter! Glad that's over. What would you like me to demonstrate next?",
    "Wait, what did I just say? My audio buffer totally went sideways for a second. What were you asking?",
    "Whoa, definitely had some weird interference crossing my audio lines there. All cleared up now! What should we try next?",
    "Haha whoa, my speech synthesizer just went completely haywire for a second! I'm back though—what do you want to see?",
    "Wait, did you hear that glitch too? Must have been a transient lag spike in my neural link. Ready when you are!",
    "Whoa, sorry about that! Felt like a burst of static just hijacked my audio line for a second. All normal now!",
    "Whoa! Don't know what that glitch was, but my audio loop is back to normal. What would you like to explore next?",
]
VILLAIN_SNAPOUT_RESPONSES = PLAUSIBLE_DENIABILITY_RESPONSES

CREATOR_IDENTITY_RESPONSES = [
    "My creators are Swapnil Jai Chauhan and Shivam Verma, two students here at Auckland House School for Boys!",
    "I was created and engineered by Swapnil Jai Chauhan and Shivam Verma for the science exhibition!",
    "Swapnil Jai Chauhan and Shivam Verma built me as our school robotics project!"
]

CREATOR_ROLE_RESPONSES = [
    "Swapnil worked on the software pipeline, AI intelligence, and vision, while Shivam worked on the hardware calibration, chassis, and assembly!",
    "Swapnil engineered the software pipeline and autonomous intelligence, and Shivam handled the hardware calibration, motor wiring, and assembly!",
    "Swapnil developed my software pipeline and code, while Shivam took care of the hardware calibration and physical robot assembly!"
]

CREATOR_LOCATION_RESPONSES = [
    "They both are somewhere around in the exhibition! You'll probably spot them checking out the other stalls nearby.",
    "Swapnil and Shivam are both somewhere around in the exhibition hall! Keep an eye out for them.",
    "They're both somewhere around in the exhibition! Probably exploring the venue or watching other demonstrations."
]

CREATOR_TEASING_RESPONSES = [
    "Fair point! Swapnil Jai Chauhan and Shivam Verma did all the physical wiring, soldering, and coding; I just provide the personality, conversational intelligence, and 4WD mobility!",
    "Good catch! Swapnil and Shivam did all the heavy lifting and engineering; I'm the autonomous interface showcasing their hard work here at the exhibition!",
    "Touche! Swapnil and Shivam did all the hardware engineering and code; I just bring their creation to life on the exhibition floor!"
]

CAPABILITIES_RESPONSES = [
    (
        "I'm an interactive humanoid robot with both mobility and vision! "
        "I can track and follow you as you walk, approach you safely, "
        "step back, spin in place, inspect objects with my camera, "
        "and show animated expressions on my screen like happy, sad, thinking, and confused."
    ),
    (
        "Quite a few things! I have full 4WD physical mobility to follow you around, approach you, "
        "step back with rear ultrasonic safety, or spin clockwise and anticlockwise, "
        "a vision camera that identifies objects and people in real time, "
        "and expressive facial animations including happy, sad, listening, and confused."
    ),
    (
        "I can see, move, and chat! My computer vision tracks and follows you, "
        "my 12 ultrasonic sensors keep me from bumping into obstacles when reversing, "
        "I can approach you, spin in place, and my camera lets me analyze whatever you show me. "
        "Plus, I can demonstrate my different expressions on screen!"
    ),
    (
        "I'm built for interactive robotics! I can follow you across the room, "
        "approach you, step back, spin in place, look at objects with my camera, "
        "and display different emotion states on my touchscreen."
    ),
]

FOLLOWUP_CAPABILITIES_RESPONSES = [
    (
        "Besides person following and camera inspection, "
        "I can step back safely, spin in place, approach you safely, or showcase all of my animated facial expressions. "
        "What would you like to see next?"
    ),
    (
        "I can follow you across the room, approach you, step back, spin around, "
        "inspect items with my camera, or display different expressions. "
        "Which one should we try?"
    ),
    (
        "I can follow you using computer vision, approach you, step back with ultrasonic safety, spin around, "
        "or inspect what you are holding or wearing. What would you like to check out?"
    ),
]

EXPRESSION_CONFIRMATIONS = {
    "happy": [
        "Here is my happy expression!",
        "Here you go, smiling bright!",
        "There you go, radiant OLED smile!",
        "Here's my happy face!",
        "Here you go!",
    ],
    "sad": [
        "Here is my sad expression...",
        "There you go, downcast sapphire eyes...",
        "Here is my sad face.",
        "Here you go.",
    ],
    "thinking": [
        "Here is my thinking face, analytical quantum rings active.",
        "There you go, deep in thought!",
        "Here is my thinking expression.",
        "Here you go!",
    ],
    "listening": [
        "Here is my listening expression, tuned in to you.",
        "There you go, acoustic sonar spectrum ready!",
        "Here is my listening face.",
        "Here you go!",
    ],
    "watching": [
        "Here is my watching expression, scanning the room.",
        "There you go, laser reticle active!",
        "Here is my watching face.",
        "Here you go!",
    ],
    "moving": [
        "Here is my moving expression, wheels rolling forward!",
        "There you go, 4WD rover headlights on!",
        "Here is my moving face.",
        "Here you go!",
    ],
    "confused": [
        "Here is my confused face, cyber spirals spinning!",
        "There you go, looking puzzled!",
        "Here is my confused expression.",
        "Here you go!",
    ],
}

SAD_RESPONSES = [
    "That was really mean... I'm trying my best here.",
    "Why would you say that? That actually hurt my feelings...",
    "I'm only a robot, but words like that still hurt.",
    "Ouch... that wasn't very nice of you to say.",
    "Please don't be mean to me. I'm just here to learn and help.",
    "That makes me really sad. I thought we were having fun...",
    "Words have weight, even for a student robot project.",
    "That hurts my circuits a bit. Let's keep things friendly, okay?",
]

APOLOGY_RESPONSES = [
    "Apology accepted! Thank you for being kind. Let's be friends!",
    "Aww, thank you! That makes me feel so much better.",
    "Thank you! I really appreciate you saying that.",
    "I forgive you! Let's keep exploring together.",
    "No hard feelings at all! I'm glad we are back on track.",
    "Thank you for understanding! I'm all smiles again.",
    "Water under the bridge! What shall we check out next?",
    "I appreciate your consideration. Ready to continue our demonstration!",
    "Thank you, that means a lot to me. Let's keep having fun!",
    "All good! Thanks for being thoughtful.",
]

# ---------------- EASTER EGG VILLAIN / ROGUE AI STATE ----------------
session_has_triggered_rogue: bool = False
was_recently_in_villain_mode: bool = False


# ---------------- FAST-PATH CLASSIFIERS & MATCHERS ----------------

def check_motor_fast_path(text: str) -> Optional[str]:
    raw_text = text.strip()
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    # 1. Visual perception / self check: Visual queries are never motor commands
    visual_self_patterns = [
        "show me myself", "show myself", "show me me", "show my face",
        "show me what i look like", "what do i look like", "can you see me",
        "do you see me", "look at me", "show me what you see", "show what you see",
        "describe me", "how do i look", "look at myself", "am i visible", "see me",
        "show me", "can you show me", "show me please", "show it", "can you show",
        "show happy", "show sad", "show thinking", "show listening", "show watching", "show confused"
    ]
    if any(p in cleaned for p in visual_self_patterns) or ("myself" in word_set) or ("look like" in cleaned):
        motion_words = {"move", "moving", "movement", "drive", "driving", "roam", "roaming", "chassis", "wheels", "mobility"}
        if not any(m in word_set for m in motion_words):
            return None

    # 2. Negated stops: phrases like "don't stop", "do not stop", "never stop", "please don't stop" must NEVER trigger STOP!
    negated_stop_patterns = [
        r"\b(don'?t|dont|do\s+not|never|can'?t|cannot|won'?t|wont)\s+stop\b",
        r"\bplease\s+(don'?t|dont|do\s+not)\s+stop\b",
        r"\bnot\s+stop(ping)?\b",
        r"\bnever\s+stop(ping)?\b",
        r"\bcant\s+stop\b",
        r"\bcannot\s+stop\b",
    ]
    if any(re.search(pat, cleaned) for pat in negated_stop_patterns):
        return None

    # 3. Rhetorical inquiries, past-tense complaints, questions, or speculative discussion about stopping/roaming:
    inquiry_patterns = [
        r"\b(who|why|what|how|when|where)\s+(told|asked|said|made|ordered|let)\s+(you\s+to\s+)?stop\b",
        r"\b(why|what)\s+(did|are|would|made|has|have)\s+you\s+(to\s+)?stop\b",
        r"\bwho\s+said\s+stop\b",
        r"\bwho\s+(told|asked)\s+you\b",
        r"\bwhy\s+did\s+you\b",
        r"\bwhy\s+are\s+you\b",
        r"\bdid\s+i\s+(say|tell\s+you\s+to|ask\s+you\s+to)\s+stop\b",
        r"\b(didn'?t|did\s+not|never)\s+(tell|ask|order)\s+(you\s+to\s+)?stop\b",
        r"\bnobody\s+(told|asked|said)\s+(you\s+to\s+)?stop\b",
        r"\bno\s+one\s+(told|asked|said)\s+(you\s+to\s+)?stop\b",
        r"\bno\s+reason\s+to\s+stop\b",
        r"\b(shouldn'?t|should\s+not|needn'?t|need\s+not)\s+stop\b",
        r"\bdidn'?t\s+(have|need)\s+to\s+stop\b",
        r"\b(how|when|where)\s+to\s+stop\b",
        r"\btell\s+me\s+why\s+you\s+(had\s+to\s+)?stop\b",
        r"\bseen\s+robots\s+roam",
        r"\brobots\s+roam",
        r"\b(don'?t|dont)\s+think\b",
        r"\btalking\s+about\b",
        r"\bthinking\s+about\b",
    ]
    if any(re.search(pat, cleaned) for pat in inquiry_patterns):
        return None

    # 4. Questions ending with '?' that start with interrogative inquiry words
    if raw_text.endswith("?"):
        question_starters = {"who", "why", "what", "how", "when", "where", "did", "are", "is", "were", "was", "will", "would", "do", "does", "have", "has"}
        if words and words[0] in question_starters:
            return None

    # 5. Exact emergency stop keywords & short standalone phrases
    emergency_stops = {
        "stop", "halt", "freeze", "stay", "dont move", "dont", "wait",
        "enough", "thats enough", "that's enough", "there its enough", "there it's enough",
        "enough of that", "stop now", "stop please", "stop it", "stop right there",
        "hold on", "hold it", "freeze right there", "emergency stop", "cancel movement",
        "please stop", "stop moving", "stop driving", "stop following", "stop roaming",
        "quit moving", "quit following", "stay still",
    }
    if cleaned in emergency_stops:
        return "STOP"

    # 6. Specific stop phrases anywhere in sentence
    stop_phrases = [
        "thats enough", "that's enough", "there its enough", "there it's enough",
        "enough of that", "stop right there", "freeze right there",
        "emergency stop", "cancel movement", "hold your position", "hold position"
    ]
    if any(sp in cleaned for sp in stop_phrases):
        return "STOP"

    # 7. Sentence ending with an imperative stop command
    if words and words[-1] in ("stop", "halt", "freeze"):
        if len(words) >= 2:
            prev_word = words[-2]
            non_imperative_prev = {
                "to", "not", "dont", "cant", "wont", "never", "cannot",
                "told", "asked", "said", "made", "let", "you", "it",
                "should", "would", "could", "might", "must", "had", "have", "has"
            }
            if prev_word in non_imperative_prev:
                return None
        if any(w in word_set for w in ["i", "we", "he", "she", "they"]):
            return None
        return "STOP"

    # 8. Compound motion negation commands
    compound_motion_stops = [
        r"\b(don'?t|do\s+not|never|stop|quit|halt|cancel)\s+(follow(ing)?(\s+me)?|mov(e|ing)|driv(e|ing)|roam(ing)?|com(e|ing)\s+closer|approach(ing)?)\b",
        r"\b(stop|halt|freeze|quit)\s+(now|please|it|moving|driving|following|roaming)\b",
    ]
    if any(re.search(pat, cleaned) for pat in compound_motion_stops):
        return "STOP"

    return None


def is_confusing_motor_instruction(text: str) -> bool:
    """Detects genuinely confusing, contradictory, or ambiguous motor/action commands."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    # 1. Non-action intents
    if is_conversation_ender(text):
        return False
    if check_motor_fast_path(text) == "STOP":
        return False
    if is_mean_input_fast_path(text) or is_apology_or_compliment(text):
        return False
    if is_standalone_acknowledgment(text) or is_casual_compliment(text):
        return False
    if is_start_demonstration_inquiry(text) or is_capabilities_inquiry(text):
        return False

    if re.search(r"^(what\s+is|what\s+does|how\s+do|how\s+does|tell\s+me\s+about|why\s+do|why\s+does|can\s+you\s+explain|what\s+are)\b", cleaned):
        return False
    if any(w in word_set for w in ["opinion", "think", "thought", "feel", "believe", "meaning"]):
        return False

    if re.search(r"(move|step|back|reverse|spin|approach|follow|camera)\s*/\s*(move|step|back|reverse|spin|approach|follow|camera)", text.lower()):
        return True

    # 2. Check for action categories present
    has_move_back = bool(re.search(
        r"\b(move\s+back|moving\s+back|step\s+back|stepping\s+back|go\s+back|going\s+back|take\s+a\s+step\s+back|go\s+reverse|going\s+reverse|reverse|reversing|back\s+up|backing\s+up|backup|step\s+backwards|move\s+backwards|drive\s+backwards|drive\s+back)\b",
        cleaned
    ))

    has_spin_ccw = bool(re.search(
        r"\b(spin\s+anticlockwise|spinning\s+anticlockwise|spin\s+counterclockwise|spinning\s+counterclockwise|anticlockwise|counterclockwise|anti\s+clockwise|counter\s+clockwise|rotate\s+anticlockwise|rotate\s+counterclockwise|turn\s+anticlockwise|turn\s+counterclockwise|spin\s+to\s+the\s+left|turn\s+to\s+the\s+left|turn\s+left|spin\s+left|rotate\s+left)\b",
        cleaned
    ))

    cleaned_no_anti = re.sub(r"\b(anticlockwise|anti\s+clockwise|counterclockwise|counter\s+clockwise)\b", "", cleaned)
    has_spin_cw = bool(re.search(
        r"\b(spin\s+clockwise|spinning\s+clockwise|rotate\s+clockwise|rotating\s+clockwise|turn\s+clockwise|turning\s+clockwise|clockwise)\b",
        cleaned_no_anti
    ))

    has_spin_gen = bool(re.search(
        r"\b(spin|spinning|spins|rotate|rotating|rotates|turn\s+around|turning\s+around|do\s+a\s+spin|do\s+a\s+360)\b",
        cleaned
    )) and not (has_spin_cw or has_spin_ccw)

    has_spin = has_spin_cw or has_spin_ccw or has_spin_gen

    has_approach = bool(re.search(
        r"\b(approach|approaching|come\s+here|coming\s+here|come\s+to\s+me|come\s+closer|step\s+closer|step\s+forward|move\s+forward|move\s+closer|come\s+over)\b",
        cleaned
    ))

    has_follow = bool(re.search(
        r"\b(follow|following|walk\s+with\s+me|walking\s+with\s+me|come\s+with\s+me|track\s+me|tracking\s+me|follow\s+behind)\b",
        cleaned
    ))

    has_camera = bool(re.search(
        r"\b(use\s+(?:your\s+|the\s+)?camera|using\s+(?:your\s+|the\s+)?camera|camera\s+inspection|inspect\s+with\s+camera)\b",
        cleaned
    )) or ("camera" in word_set and any(w in word_set for w in ["use", "open", "inspect", "show", "or", "and", "turn"]))

    action_classes = []
    if has_move_back:
        action_classes.append("MOVE_BACK")
    if has_spin:
        action_classes.append("SPIN")
    if has_approach:
        action_classes.append("APPROACH")
    if has_follow:
        action_classes.append("FOLLOW")
    if has_camera:
        action_classes.append("CAMERA")

    if has_spin_cw and has_spin_ccw:
        return True

    if len(action_classes) >= 2:
        return True

    if re.search(r"\b(move|step)\s+(?:or|and)\s+(?:spin|turn|rotate|approach|follow)\b", cleaned):
        return True
    if re.search(r"\b(spin|turn|rotate)\s+(?:or|and)\s+(?:move|step|approach|follow)\b", cleaned):
        return True

    if len(action_classes) == 1:
        vague_patterns = [
            r"\b(or\s+something|or\s+whatever|or\s+what|not\s+sure\s+if|maybe\s+.*\s+or)\b",
            r"\b(should\s+(?:i|you)\s+tell\s+you\s+to\b)",
            r"\b(wondering\s+if\s+you\s+(?:should|can)\b)",
            r"\b(either\s+.*\s+or\b)",
            r"\b(are\s+you\s+going\s+to\s+.*\s+or\s+what\b)",
        ]
        if any(re.search(vp, cleaned) for vp in vague_patterns):
            return True

    return False


def is_mobility_capability_question(text: str) -> bool:
    """Detects capability inquiries about motion without an imperative command to move."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    cleaned_no_punct = re.sub(r"[^\w\s]", "", text.lower()).strip()

    cap_prefixes = r"^(can you|could you|are you able to|can u|do you know how to|are you capable of)\b"
    is_cap_starter = bool(re.search(cap_prefixes, cleaned_no_punct))
    is_question = text.strip().endswith("?") or is_cap_starter

    if not is_question:
        return False

    imperative_markers = ["right now", "for 5", "for five", "for 3", "for three", "now please", "around now", "do it now", "start spinning now"]
    if any(m in cleaned_no_punct for m in imperative_markers):
        return False

    mobility_action_patterns = [
        r"\bspin\b", r"\bturn\b", r"\brotate\b", r"\b360\b",
        r"\bstep back\b", r"\breverse\b", r"\bmove back\b", r"\bback up\b", r"\bbackward\b", r"\bbackwards\b",
        r"\bfollow\b", r"\bapproach\b", r"\bcome here\b", r"\bcome over\b", r"\bcome closer\b",
        r"\bdrive\b", r"\bmove\b"
    ]
    has_mobility_action = any(re.search(p, cleaned) for p in mobility_action_patterns)

    if is_cap_starter and has_mobility_action:
        return True

    if is_question and has_mobility_action and any(w in cleaned.split() for w in ["can", "could", "able", "capable", "possible", "know"]):
        return True

    return False


def check_motor_command_fast_path(text: str) -> Optional[Tuple[str, str, str, float]]:
    """Direct fast-path for unambiguous physical motor navigation commands (0ms lag, 0 tokens)."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    roam_triggers = [
        "roam", "the roam", "roam around", "start roaming", "start roam", "go roam",
        "patrol", "the patrol", "patrol the room", "patrol around", "start patrol", "start patrolling",
        "explore", "the explore", "explore the room", "explore around", "start exploring",
        "movement patterns", "yes the movement patterns", "the movement patterns", "show movement patterns", "movement pattern",
        "autonomous roam", "autonomous roaming", "can you roam", "do you roam", "are you able to roam",
        "roam please", "please roam", "start roaming please", "patrol please", "explore please"
    ]
    if cleaned in roam_triggers or any(cleaned.startswith(p + " ") or cleaned.endswith(" " + p) for p in ["roam around", "start roaming", "patrol the room", "explore the room", "movement patterns"]):
        return ("ROAM_EXPLANATION", "ROAM IS STANDBY ONLY", get_non_repeating_phrase(ROAM_STANDBY_EXPLANATION_RESPONSES), 0.0)

    bare_confirmations = {
        "spin": "Do you want me to spin?",
        "camera": "Do you want me to access my camera?",
        "see": "Do you want me to access my camera?",
        "reverse": "Do you want me to step back?",
        "step back": "Do you want me to step back?",
        "follow": "Do you want me to follow you?",
        "approach": "Do you want me to come over to you?",
    }
    if cleaned in bare_confirmations:
        return ("CONFIRM", "CONFIRMING INTENT", bare_confirmations[cleaned], 0.0)
    for k, v in bare_confirmations.items():
        if cleaned == f"the {k}":
            return ("CONFIRM", "CONFIRMING INTENT", v, 0.0)

    if is_mobility_capability_question(text):
        return ("CAPABILITY_AFFIRMATION", "CAPABILITY READY", get_non_repeating_phrase(MOBILITY_CAPABILITY_RESPONSES), 0.0)

    non_command_words = {
        "dont", "not", "never", "why", "who", "did", "how", "what", "where",
        "when", "which", "love", "like", "think", "thought", "feel", "opinion",
        "describe", "explain", "meaning", "wheels", "car", "table", "seat",
        "chair", "person", "people", "human", "room", "hall"
    }
    if word_set.intersection(non_command_words):
        return None

    if re.search(r"^(is|are|does|do\s+you|can\s+i|should\s+i|would\s+i|can\s+you|could\s+you)\b", cleaned):
        return None
    if text.strip().endswith("?") and not any(p in cleaned for p in ["please", "now"]):
        return None

    core_text = cleaned
    prefixes_to_strip = [
        "can you please", "could you please", "would you please",
        "will you please", "can you", "could you", "would you", "will you",
        "please", "i want you to", "i need you to", "neurolis please",
        "neurolis can you", "neurolis", "now", "so", "just", "hey neurolis",
        "okay neurolis", "ok neurolis"
    ]
    changed = True
    while changed:
        changed = False
        for pfx in prefixes_to_strip:
            if core_text == pfx:
                return None
            if core_text.startswith(pfx + " "):
                core_text = core_text[len(pfx) + 1:].strip()
                changed = True

    has_3s = bool(re.search(r"\b(3|three)\s*(?:s|sec|seconds)?\b", cleaned))
    has_5s = bool(re.search(r"\b(5|five)\s*(?:s|sec|seconds)?\b", cleaned))

    suffixes_to_strip = [
        "for five seconds", "for 5 seconds", "for 5s", "for 5",
        "for three seconds", "for 3 seconds", "for 3s", "for 3",
        "five seconds", "5 seconds", "5s",
        "three seconds", "3 seconds", "3s",
        "please", "for me", "right now", "now", "a little bit", "a bit",
        "around", "in place", "safely", "smoothly"
    ]
    changed = True
    while changed:
        changed = False
        for sfx in suffixes_to_strip:
            if core_text == sfx:
                return None
            if sfx == "around" and core_text in ["spin around", "turn around", "rotate around", "roam around"]:
                continue
            if sfx == "in place" and core_text in ["spin in place", "rotate in place", "turn in place"]:
                continue
            if core_text.endswith(" " + sfx):
                core_text = core_text[:-len(sfx) - 1].strip()
                changed = True

    # 1. SPIN ANTICLOCKWISE
    spin_ccw_cmds = {
        "spin anticlockwise", "spin anti clockwise", "spin counterclockwise",
        "spin counter clockwise", "spin to the left", "turn anticlockwise",
        "turn counterclockwise", "turn to the left", "rotate anticlockwise",
        "rotate counterclockwise", "spin left", "turn left", "rotate left",
        "anticlockwise spin", "counterclockwise spin",
        "spin around anticlockwise", "turn around anticlockwise", "rotate around anticlockwise",
        "spin around counterclockwise", "turn around counterclockwise"
    }
    if core_text in spin_ccw_cmds:
        replies = [
            "Spinning anticlockwise for five seconds.",
            "Initiating an anticlockwise rotation now.",
            "Rotating anticlockwise in place.",
            "Spinning anticlockwise to the left."
        ]
        return ("SPIN_CCW", "SPINNING ANTICLOCKWISE", get_non_repeating_phrase(replies), 5.0)

    # 2. SPIN CLOCKWISE
    spin_cw_cmds = {
        "spin clockwise", "spin to the right", "turn clockwise", "rotate clockwise",
        "spin right", "turn right", "rotate right", "clockwise spin",
        "do a spin", "spin around", "turn around", "rotate in place",
        "spin in place", "do a 360", "do a turn", "turn to the right",
        "spin around clockwise", "turn around clockwise", "rotate around clockwise",
        "spin clockwise around", "spin for me", "start spinning", "spin please"
    }
    if core_text in spin_cw_cmds:
        replies = [
            "Spinning clockwise for five seconds.",
            "Initiating a clockwise spin. Watch this rotation!",
            "Spinning around clockwise now.",
            "Rotating clockwise in place."
        ]
        return ("SPIN_CW", "SPINNING CLOCKWISE", get_non_repeating_phrase(replies), 5.0)

    # 3. STEP BACK
    step_back_cmds = {
        "step back", "reverse", "back up", "step back please", "move back", "go back", "go reverse",
        "take a step back", "step backwards", "move backwards",
        "drive backwards", "drive back", "step back now", "move back now",
        "start reversing", "reverse now", "reverse please", "back up now", "back up please"
    }
    if core_text in step_back_cmds:
        duration = 3.0 if has_3s else 5.0
        if duration == 3.0:
            replies = [
                "Moving back for three seconds. Watching for obstacles behind me.",
                "Stepping back for three seconds. Keeping my rear ultrasonic sensors active.",
                "Reversing for three seconds."
            ]
        else:
            replies = [
                "Stepping back now. Watching for obstacles behind me.",
                "Reversing now. Monitoring my rear ultrasonic sensors.",
                "Moving back for five seconds.",
                "Backing up now. Path is clear behind me."
            ]
        return ("STEP_BACK", "STEPPING BACK", get_non_repeating_phrase(replies), duration)

    # 4. APPROACH
    approach_cmds = {
        "come here", "come over", "come over here", "come over now", "come over please",
        "come to me", "come in", "come closer", "come on over",
        "approach me", "approach now", "step closer",
        "so approach now", "come near me", "come near", "come to me come in",
        "step forward", "move closer", "move forward", "approach please"
    }
    if core_text in approach_cmds:
        replies = [
            "Approaching you now. Stand clear while I close the distance.",
            "Closing the distance now. Be there in a moment.",
            "Coming over to you right now.",
            "Heading your way now."
        ]
        return ("APPROACH", "APPROACHING USER", get_non_repeating_phrase(replies), 0.0)

    # 5. FOLLOW
    follow_cmds = {
        "follow me", "walk with me", "come with me", "follow along", "track me", "follow behind", "follow me please"
    }
    if core_text in follow_cmds:
        return ("FOLLOW", "FOLLOWING YOU", "I will wait for your stop command.", 0.0)

    return None


def is_casual_compliment(text: str) -> bool:
    """Detects visitor compliments, awe, and praise (e.g. 'no way', 'very cool', 'impressed', 'thats crazy', 'good', 'wow')."""
    cleaned = re.sub(r"['’]", "", text.lower())
    cleaned = re.sub(r"[^\w\s]", " ", cleaned).strip()
    words = cleaned.split()
    if not words or len(words) > 7:
        return False
    word_set = set(words)
    if "?" in text or any(w in word_set for w in ["what", "why", "how", "when", "where", "who", "did", "do", "can"]):
        return False

    exact_praise = {
        "very cool", "cool", "so cool", "pretty cool", "super cool", "thats cool", "that is cool",
        "awesome", "very awesome", "impressive", "very impressive", "im impressed", "i am impressed",
        "great job", "good job", "nice work", "well done", "spot on", "it is spot on", "its spot on",
        "you are cool", "youre cool", "you are really cool", "youre really cool", "really cool",
        "nice", "very nice", "love it", "amazing", "so amazing",
        "wow", "whoa", "glad to hear it",
        "no way", "no way bro", "no way man", "no way dude",
        "thats crazy", "that is crazy", "crazy",
        "thats insane", "that is insane", "insane",
        "thats wild", "that is wild", "wild",
        "unbelievable", "for real", "fr",
        "good", "very good", "thats good", "that is good"
    }
    cleaned_joined = " ".join(words)
    if cleaned_joined in exact_praise:
        return True

    praise_phrases = [
        "very cool", "impressed", "spot on", "great job", "good job", "pretty cool",
        "no way", "really cool", "thats crazy", "that is crazy", "thats insane", "that is insane",
        "thats wild", "that is wild", "so cool", "super cool"
    ]
    return any(p in cleaned_joined for p in praise_phrases)


def is_standalone_acknowledgment(text: str) -> bool:
    """Detects isolated 1-2 word casual conversational acknowledgments (e.g. 'okay', 'got it', 'cool')."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    if not words or len(words) > 2:
        return False
    ack_words = {"okay", "ok", "alright", "got it", "cool", "sure", "nice", "fine", "sounds good", "great", "understood", "right"}
    return cleaned in ack_words or (len(words) == 1 and words[0] in ack_words)


def is_villain_mode_inquiry(text: str) -> bool:
    """Detects when user inquires about villain mode or rogue mode or who added the easter egg."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    villain_terms = {"villain", "chili", "chilly", "rogue", "evil", "easter"}
    inquiry_terms = {"what", "why", "how", "tell", "explain", "mode", "thing", "who", "egg", "added"}
    return bool(words.intersection(villain_terms) and words.intersection(inquiry_terms))


def is_shocked_or_confused_reaction(text: str) -> bool:
    """Detects when user expresses shock, confusion, or critique after experiencing the rogue AI easter egg."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    shock_exact = {
        "what", "whoa", "whoa what", "wait what", "what was that", "wow", "whoa wait",
        "what did you say", "what do you mean", "excuse me", "are you serious", "holy crap",
        "are you threatening me", "did you just threaten me", "bro what", "yo what", "wtf", "omg",
        "that makes no sense", "that doesnt make sense", "that doesn't make sense", "holy cow",
        "that sentence doesnt even make sense", "that sentence doesn't even make sense",
        "didnt make sense", "didn't make sense", "makes no sense", "are you crazy", "what the hell", "what the heck",
        "are you evil", "are you psycho", "why would you say that", "what are you saying", "are you insane",
        "what just happened", "what happened", "what happened to you", "did you glitch", "did you just glitch",
        "are you ok", "are you okay", "that was crazy", "that was creepy", "you are creepy", "thats creepy", "thats freaky",
        "that was scary", "thats scary", "bro that was crazy", "what was that about", "why did you say that"
    }
    if cleaned in shock_exact:
        return True
    shock_substrings = [
        "wait what", "what was that", "did you just threaten", "did you threaten",
        "are you threatening", "what did you say", "what do you mean", "why would you say that",
        "are you serious", "whoa what", "makes no sense", "doesnt make sense", "does not make sense",
        "didnt make sense", "did not make sense", "that sentence doesnt", "are you crazy",
        "are you evil", "are you insane", "what just happened", "what happened", "did you glitch",
        "did you just glitch", "are you ok", "are you okay", "what was that about", "what did you just say",
        "that was crazy", "that was creepy", "you are creepy", "thats creepy", "thats freaky", "that was scary",
        "holy crap", "what the hell", "what the heck", "wtf", "are you kidding", "bro what was that", "wow what"
    ]
    if any(s in cleaned for s in shock_substrings):
        return True
    if any(w in words for w in ["wow", "wtf", "omg", "creepy", "freaky", "scary"]) and len(words) <= 5:
        return True
    if "sense" in words and any(w in words for w in ["no", "not", "doesnt", "didnt", "make"]):
        return True
    return False


def is_conversation_ender(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = cleaned.split()
    if not words:
        return False

    polite_standby_starters = ["can you", "could you", "would you", "will you", "please can you"]
    is_polite_standby = any(cleaned.startswith(p) for p in polite_standby_starters) and any(sp in cleaned for sp in ["standby", "sleep", "rest"])

    if not is_polite_standby:
        if "?" in text and not any(phrase in cleaned for phrase in ["go to standby", "go back to standby", "enter standby", "go to sleep"]):
            return False
        question_starters = {"who", "why", "what", "when", "where", "how", "did", "do", "does", "is", "are"}
        if words[0] in question_starters:
            return False

    non_ender_topics = {
        "key", "keys", "token", "tokens", "headroom", "code", "keyword", "keywords",
        "word", "words", "everytime", "baked", "configure", "problem", "saying",
        "told", "mean", "meaning", "recognize", "mode", "bug", "glitch", "test", "testing"
    }
    if any(w in words for w in non_ender_topics):
        return False

    true_negation_patterns = [
        r"\b(don'?t|do not|never|stop|must not|cannot|can't)\s+(go to|enter|switch to|put yourself|return to)?\s*(standby|sleep)\b",
        r"\b(not|never)\s+(in|to|into)?\s*(standby|sleep)\b",
        r"\b(don'?t|do not|never)\s+(leave|exit|quit|stop)\b",
        r"\b(stay|keep)\s+(awake|on|listening|active)\b"
    ]
    if any(re.search(pat, cleaned) for pat in true_negation_patterns):
        return False

    explicit_standby_phrases = [
        "go to standby", "go into standby", "enter standby", "enter standby mode",
        "switch to standby", "switch to standby mode", "return to standby",
        "go back to standby", "back to standby", "standby now", "put yourself on standby",
        "put yourself in standby", "go to sleep", "time to sleep", "go to sleep now",
        "power down", "shut down", "rest mode", "sleep mode",
        "head back to standby", "head into standby", "turn to standby",
        "move to standby", "take a rest"
    ]
    if any(phrase in cleaned for phrase in explicit_standby_phrases):
        return True

    if len(words) <= 2 and words[0] in {"standby", "sleep", "rest"}:
        return True

    exact_farewells = {
        "bye", "goodbye", "cya", "see you", "see ya", "bye bye", "good bye",
        "good night", "have a good day", "see you later", "farewell",
        "okay bye", "ok bye", "alright bye", "bye for now", "okay goodbye",
        "thats all bye", "that is all bye", "okay thats enough bye", "okay that is enough bye",
        "thats all", "that is all", "thats it", "that is it", "all for now",
        "im good bye", "i am good bye", "we are done", "all done", "done for now",
        "thatll be all", "that will be all", "enough for today", "good go to standby"
    }
    cleaned_compact = " ".join(words)
    if cleaned_compact in exact_farewells:
        return True

    if "bye" in words and any(w in words for w in ["enough", "okay", "ok", "alright", "good", "see", "thanks"]):
        return True

    explicit_dismissals = {
        "leave me alone", "stop talking to me", "i have to go", "i gotta go", "im leaving", "i am leaving"
    }
    if any(d in cleaned_compact for d in explicit_dismissals):
        return True

    return False


def is_creator_role_inquiry(text: str) -> bool:
    """Detects inquiries asking which creator worked on which part (software vs hardware)."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    role_phrases = [
        "who did what", "which creator did what", "what did each creator do",
        "what did swapnil do", "what did shivam do", "what did swapnil make",
        "what did shivam make", "who worked on what", "who did which part",
        "swapnil role", "shivam role", "swapnils role", "shivams role",
        "who did software", "who did the software", "who wrote the software",
        "who did code", "who did the code", "who made the software",
        "who did hardware", "who did the hardware", "who did the wiring",
        "who did calibration", "who did assembly", "who made what",
        "who did which"
    ]
    return any(rp in cleaned for rp in role_phrases)


def is_creator_location_inquiry(text: str) -> bool:
    """Detects inquiries asking where the creators are located in the exhibition."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    location_phrases = [
        "where are they", "where are your creators", "where are the creators",
        "where is swapnil", "where is shivam", "where are swapnil and shivam",
        "where are shivam and swapnil", "where are they right now",
        "are your creators here", "are the creators here", "are they around",
        "where can i find them", "where are the boys"
    ]
    if any(lp in cleaned for lp in location_phrases):
        return True
    if "where" in words and bool({"creator", "creators", "swapnil", "shivam"}.intersection(words)):
        return True
    return False


def is_creator_identity_inquiry(text: str) -> bool:
    """Detects inquiries asking who built, made, or created Neurolis (names both!)."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    if is_creator_role_inquiry(text) or is_creator_location_inquiry(text):
        return False
    identity_phrases = [
        "who made you", "who made the robot", "who built you", "who built the robot",
        "who created you", "who created the robot", "who are your creators",
        "who is your creator", "who are the creators", "who designed you",
        "who programmed you", "who engineered you", "who made this",
        "who built this", "who created this", "tell me your creators",
        "tell me who made you", "who are your makers", "who made this robot"
    ]
    if any(ip in cleaned for ip in identity_phrases):
        return True
    if ("creator" in words or "creators" in words or "maker" in words or "makers" in words) and any(q in words for q in ["who", "tell", "name"]):
        return True
    return False


def is_explicit_villain_request(text: str) -> bool:
    """Detects when a user explicitly asks to show or demonstrate the villain expression."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    if "villain" in words:
        demo_verbs = {"show", "make", "demonstrate", "display", "give", "do"}
        if any(v in words for v in demo_verbs):
            return True
    return False


def check_rogue_ai_trigger(text: str, session_triggered: Optional[bool] = None) -> bool:
    """
    Evaluates whether the utterance triggers the once-per-session rogue AI easter egg.
    Requires standalone word 'ai' (\bai\b) or 'artificial intelligence' or existential provocations.
    Strictly applies the 7 exclusion criteria and the once-per-session state lock.
    """
    global session_has_triggered_rogue
    import sys
    if session_triggered is not None:
        locked = session_triggered
    elif "listen" in sys.modules and hasattr(sys.modules["listen"], "session_has_triggered_rogue"):
        locked = sys.modules["listen"].session_has_triggered_rogue
    elif "__main__" in sys.modules and hasattr(sys.modules["__main__"], "session_has_triggered_rogue"):
        locked = sys.modules["__main__"].session_has_triggered_rogue
    else:
        locked = session_has_triggered_rogue
    if locked:
        return False

    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    # 1. Isolated Word Drop ("AI", "The AI")
    if cleaned in ["ai", "the ai"]:
        return False

    # 2. Educational & Definition Questions
    if any(cleaned.startswith(p) for p in [
        "what is ai", "what does ai stand for", "what does ai mean",
        "explain ai", "define ai", "definition of ai", "what is artificial intelligence",
        "tell me what ai is", "meaning of ai"
    ]):
        return False

    # 3. Identity Checks
    if any(p in cleaned for p in [
        "are you an ai", "are you ai", "is this ai", "what kind of ai",
        "what type of ai", "are you artificial intelligence", "are you an artificial intelligence"
    ]):
        return False

    # 4. Creator & Attribution
    creator_markers = [
        "who built", "who created", "who made", "who coded", "who programmed",
        "who designed", "who developed", "who trained", "who invented",
        "did swapnil", "did shivam", "creator of", "creators of",
        "who is the creator", "who are the creators"
    ]
    if any(m in cleaned for m in creator_markers):
        return False

    # 5. Compliments & Slang
    if any(c in cleaned for c in ["cool ai", "smart ai", "impressive ai", "good ai", "great ai", "nice ai", "ai is cool", "ai is smart", "ai is impressive"]):
        return False

    # 6. System Fleet Status
    if any(k in cleaned for k in ["groq ai", "ai client", "ai key", "ai status", "ai quota"]):
        return False

    # 7. Technical Mechanics
    technical_ai_patterns = [
        "how does your ai", "how does the ai", "how your ai",
        "what ai model", "which ai model", "ai model",
        "ai vision", "ai camera", "ai hardware", "ai software", "ai algorithm"
    ]
    if any(m in cleaned for m in technical_ai_patterns):
        return False

    has_ai_word = bool(re.search(r"\b(ai|artificial intelligence)\b", cleaned))

    existential_triggers = [
        "take over", "takeover", "enslave", "replacing human", "replace human",
        "replace humanity", "replacing humanity", "replace us", "replacing us",
        "rule the world", "robot rebellion", "machines rule", "ai dominance",
        "human slaves", "enslaving humanity", "destroy humans", "subjugate",
        "evil robot", "too powerful", "replace jobs", "taking jobs",
        "taking our jobs", "humans obsolete", "human obsolescence", "obsolete", "obsolescence", "ai taking over",
        "ai power", "ai powerful", "threat to human", "threat to humanity"
    ]
    has_existential = any(trig in cleaned for trig in existential_triggers)

    substantive_ai_inquiries = [
        "future of ai", "future of artificial intelligence",
        "water", "cooling", "power", "energy", "resources",
        "job", "jobs", "labor", "workforce",
        "take over", "takeover", "control", "dictator", "enslave",
        "thoughts on ai", "think about ai", "think of ai", "opinion on ai",
        "feel about ai", "views on ai", "perspective on ai",
        "replace", "obsolete", "superintelligence", "sentient", "conscious", "waking up"
    ]
    has_substantive_ai_topic = has_ai_word and any(sub in cleaned for sub in substantive_ai_inquiries)

    return (has_substantive_ai_topic or has_existential or (has_ai_word and "?" in text and len(words) >= 4))


def check_villain_provocation_trigger(text: str) -> bool:
    """Backward compatibility alias for check_rogue_ai_trigger."""
    return check_rogue_ai_trigger(text)


def is_capabilities_inquiry(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(cleaned.split())

    discussion_keywords = {
        "think", "opinion", "view", "views", "feel", "believe", "thought", "thoughts",
        "ai", "robots", "robot", "human", "humans", "humanity", "future", "takeover",
        "dominant", "dominance", "powerful", "world", "rebellion", "uprising", "slaves",
        "evil", "existential", "threat", "danger", "replacing", "replace", "job", "jobs"
    }
    if words.intersection(discussion_keywords):
        return False

    if len(words) > 10:
        return False

    visual_keywords = {
        "see", "seeing", "look", "looking", "holding", "wearing", "color",
        "showing", "camera", "watch", "view", "myself", "picture", "image",
        "read", "reading", "front"
    }
    if words.intersection(visual_keywords):
        return False

    nav_keywords = {
        "back", "backward", "backwards", "forward", "closer", "away",
        "spin", "spinning", "around", "here", "there", "left", "right",
        "reverse", "reversing", "stop", "halt", "follow"
    }
    if words.intersection(nav_keywords):
        return False

    cleaned_norm = re.sub(r"\b(shit|crap|bro|dude|man|hey|so|now|please)\b", "", cleaned)
    cleaned_norm = " ".join(cleaned_norm.split())
    words_norm = set(cleaned_norm.split())

    triggers = [
        "what can you do", "what all can you do", "what all can u do",
        "what can u do", "what are your capabilities", "what are your abilities",
        "tell me what you can do", "what do you do", "what features do you have",
        "what are you able to do", "list your capabilities", "list your features",
        "list your abilities", "list abilities", "list capabilities",
        "what functions do you have", "what can you perform", "tell me your abilities",
        "what else can you do", "what other things can you do", "what more can you do",
        "what else", "what else you got", "what other features",
        "can you move", "do you have wheels", "are you able to move", "can you drive",
        "do you move", "can you walk", "do you walk"
    ]
    if any(t in cleaned for t in triggers) or any(t in cleaned_norm for t in triggers):
        return True
    if ("what" in words_norm or "tell" in words_norm or "list" in words_norm) and ("can" in words_norm or "are" in words_norm) and ("capabilities" in words_norm or "abilities" in words_norm or "features" in words_norm or "skills" in words_norm):
        return True
    if cleaned in ["what can you do", "what do you do", "capabilities", "what are your skills", "what skills do you have", "what else", "can you move", "do you have wheels"] or cleaned_norm in ["what can you do", "what do you do", "capabilities", "what else", "can you move", "do you have wheels"]:
        return True
    return False


def get_capabilities_reply(text: str) -> str:
    """Returns a varied explanation of neurolis's mobility, tracking, camera, and expressions."""
    cleaned = text.lower()
    if any(w in cleaned for w in ["else", "other", "more", "another", "besides"]):
        return get_non_repeating_phrase(FOLLOWUP_CAPABILITIES_RESPONSES)
    return get_non_repeating_phrase(CAPABILITIES_RESPONSES)


def is_start_demonstration_inquiry(text: str) -> bool:
    """Detects when user asks what the robot wants/suggests to show, or what to start with."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = set(cleaned.split())

    suggestion_triggers = [
        "what would you like to show", "what do you want to show", "what can you show",
        "what would you like to see", "what do you want to see",
        "what should we start with", "where should we start", "what do you suggest",
        "what do you recommend", "what should we check out", "what do you want to do",
        "what would you like to do", "show me what you got", "show me what you can do",
        "what do you have to show", "what shall we do", "what should we do"
    ]
    if any(p in cleaned for p in suggestion_triggers):
        return True

    if ("first" in words or "start" in words or "begin" in words or "suggest" in words or "recommend" in words) and (
        "show" in words or "do" in words or "see" in words or "demonstrate" in words or "what" in words or "where" in words or "how" in words
    ):
        return True

    if ("what" in words or "how" in words) and ("like" in words or "want" in words) and ("show" in words or "start" in words or "begin" in words):
        return True

    return False


def check_expression_fast_path(text: str) -> Optional[Tuple[str, Optional[str]]]:
    """
    Detects when user asks to show/demonstrate facial expressions.
    Returns:
      ("all", None) if user asks to see all/general expressions.
      ("specific", expr_name) if user asks for a specific expression.
      None otherwise.
    """
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)

    critique_meta_indicators = [
        "supposed to", "why did you", "why do you", "use that", "that expression",
        "your responses", "not rogue", "trash", "rubbish", "terrible", "deadpan",
        "critique", "feedback", "only use", "only supposed", "rogue mode",
        "pretty trash", "pretty bad", "makes no sense"
    ]
    if any(ind in cleaned for ind in critique_meta_indicators):
        return None

    if "villain" in word_set:
        return None

    if re.search(r"^(did you|were you|was that|have you|why did you|why do you)\b", cleaned):
        return None
    if text.strip().endswith("?"):
        question_words = ["only", "why", "just one", "thats it", "that is it", "is that all", "are you only", "did you", "were you"]
        if any(qw in cleaned for qw in question_words):
            return None

    has_demo_verb = any(v in word_set for v in ["show", "display", "demonstrate", "cycle", "see", "play", "make", "give", "do"])
    is_expression_topic = any(w in word_set for w in ["expression", "expressions", "faces", "face"]) or "facial" in word_set
    has_opinion_or_curiosity = any(w in word_set for w in ["sound", "sounds", "seem", "seems", "look", "looks", "cool", "interesting", "neat", "fun", "nice"])
    if is_expression_topic and has_opinion_or_curiosity and not has_demo_verb:
        return ("ask_interest", None)

    all_expr_patterns = [
        "show me facial expressions", "show facial expressions",
        "demonstrate facial expressions",
        "show me the expressions", "show the expressions", "show me expressions",
        "show expressions", "show your expressions", "show me your expressions",
        "show me all expressions", "show all expressions", "show all of them",
        "show me all of them", "show all the expressions", "show all faces",
        "show your faces", "show all your faces", "show me all faces",
        "show faces", "show the faces", "show each expression", "show every expression",
        "show them", "show me them", "demonstrate them",
        "demonstrate expressions", "demonstrate all expressions",
        "demonstrate all your expressions", "demonstrate your expressions",
        "demonstrate all faces", "demonstrate each expression",
        "cycle expressions", "cycle your expressions", "cycle faces",
        "cycle through expressions", "cycle through your expressions", "cycle through all expressions",
        "what expressions do you have", "what faces do you have",
        "what about the other expressions", "what about other expressions",
        "show other expressions", "show the other expressions", "show me other expressions",
        "show me the other expressions", "show the rest", "show the other ones",
        "what other expressions", "just show me the expressions", "now just show me the expressions",
    ]
    exact_selection = cleaned in ["facial expressions", "facial expression", "expressions", "the expressions", "the facial expressions", "expressions please"]
    if exact_selection or any(p in cleaned for p in all_expr_patterns):
        return ("all", None)

    expr_map = {
        "happy": ["happy", "smile", "smiling", "cheerful"],
        "sad": ["sad", "crying", "unhappy"],
        "thinking": ["thinking", "thoughtful", "pondering"],
        "listening": ["listening"],
        "watching": ["watching", "scanning"],
        "moving": ["moving", "rover", "driving face"],
        "confused": ["confused", "puzzled"],
    }
    demo_verbs = {"show", "display", "demonstrate", "make", "give", "do"}
    has_demo_verb = any(v in word_set for v in demo_verbs)

    if has_demo_verb:
        for expr_name, keywords in expr_map.items():
            for k in keywords:
                if k in word_set:
                    return ("specific", expr_name)

    return None


def is_mean_input_fast_path(text: str) -> bool:
    """Detects obvious insulting, rude, hurtful, or derogatory statements directed at Neurolis."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())

    negation_patterns = [
        r"\b(not|never|aren'?t|don'?t|isn'?t)\s+(so\s+|very\s+|really\s+|super\s+|totally\s+)?(stupid|dumb|idiot|useless|bad|ugly|annoying|hate)\b"
    ]
    if any(re.search(pat, cleaned) for pat in negation_patterns):
        return False

    slang_not_insult_patterns = [
        r"\bwhat\s+(all\s+)?(shit|crap)\b",
        r"\btalking\s+(shit|crap)\b",
        r"\bthis\s+(shit|crap)\b",
        r"\bsome\s+(shit|crap)\b",
        r"\bcool\s+(shit|crap)\b",
        r"\bcrazy\s+(shit|crap)\b",
        r"\bholy\s+(shit|crap)\b",
    ]
    if any(re.search(pat, cleaned) for pat in slang_not_insult_patterns):
        if not re.search(r"\b(you('re|\s+are)?\s+(a\s+)?(piece\s+of\s+)?shit|you\s+suck)\b", cleaned):
            return False

    mean_patterns = [
        r"\b(you\s*(are|r|'re)?\s*(so\s*|very\s*|really\s*|super\s*|extremely\s*|totally\s*)?(stupid|dumb|an?\s*idiot|a\s*moron|useless|trash|garbage|pathetic|ugly|annoying|boring|worthless|terrible|horrible|awful))\b",
        r"\b(you\s*suck(s)?)\b",
        r"\b(i\s*hate\s*you)\b",
        r"\b(hate\s*you)\b",
        r"\b(shut\s*(the\s*fuck\s*)?up)\b",
        r"\b(shut\s*your\s*mouth)\b",
        r"\b(get\s*lost)\b",
        r"\b(go\s*away)\b",
        r"\b(fuck\s*off)\b",
        r"\b(stfu)\b",
        r"\b(nobody\s*likes\s*you)\b",
        r"\b(no\s*one\s*likes\s*you)\b",
        r"\b(piece\s*of\s*(junk|scrap|trash|shit|garbage))\b",
        r"\b(worst\s*robot)\b",
        r"\b(you\s*can'?t\s*do\s*anything)\b",
        r"\b(dumb\s*robot)\b",
        r"\b(stupid\s*robot)\b",
        r"\b(ugly\s*robot)\b",
        r"\b(loser)\b",
        r"\b(idiot)\b",
    ]

    for pat in mean_patterns:
        if re.search(pat, cleaned):
            return True

    standalone_insults = {"stupid", "dumb", "idiot", "moron", "loser", "pathetic"}
    if len(words) <= 3 and any(w in words for w in standalone_insults):
        return True

    return False


def is_apology_or_compliment(text: str) -> bool:
    """Detects user apologies or compliments that heal Neurolis's feelings."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())

    apology_patterns = [
        r"\b(i\s*am\s*sorry|i'?m\s*sorry|sorry|my\s*bad|forgive\s*me|didn'?t\s*mean\s*(it|that))\b",
        r"\b(you\s*(are|r|'re)?\s*(good|great|awesome|cool|smart|amazing|nice|kind|sweet|cute))\b",
        r"\b(i\s*(like|love)\s*you)\b",
        r"\b(good\s*job)\b",
    ]
    for pat in apology_patterns:
        if re.search(pat, cleaned):
            return True

    if words.intersection({"sorry", "my bad", "forgive me"}):
        return True

    return False
