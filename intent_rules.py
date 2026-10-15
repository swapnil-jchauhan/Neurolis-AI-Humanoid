"""
Project Neurolis - Fast-Path Regex & Intent Classification Engine (intent_rules.py)
-----------------------------------------------------------------------------------
Houses the zero-latency, zero-token fast-path classification rules, regex patterns,
and verbatim response phrase pools for:
- Mobility inquiries & prototype explanation (remote control, student development)
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
MOBILITY_EXPLANATION_RESPONSES = [
    "I'm an early physical prototype built on a 4WD quad-motor chassis! My movement is operated via teleoperation using a handheld remote control. My student developers, Swapnil Jai Chauhan and Shivam Verma at Auckland House School for Boys, are actively developing my autonomous navigation. If you'd like to see me roll, feel free to ask our demonstrators nearby to drive me via teleoperation!",
    "My physical mobility is powered by a 4WD quad-motor chassis operated via teleoperation with a remote control. Student engineers Swapnil and Shivam are still refining my autonomous drive systems. Ask any of our student demonstrators standing around the booth to demonstrate my movement!",
    "I move across the floor on a 4WD quad-motor base controlled via teleoperation using a handheld remote. My creators, Swapnil and Shivam at Auckland House School, are actively improving my drive systems. Just ask the demonstrators around me if you want to see teleoperation in action!",
    "For this science exhibition prototype, my 4WD quad-motor chassis moves through teleoperation using a handheld remote. Swapnil Jai Chauhan and Shivam Verma are working on my autonomous upgrades—feel free to ask the demonstrators beside me to drive me around!",
    "I'm equipped with a 4WD quad-motor chassis operated via teleoperation! While my student builders, Swapnil and Shivam, continue engineering my autonomous systems, our demonstrators around the floor can demonstrate my movement with the remote whenever you ask.",
    "My movement runs on a 4WD quad-motor drive system controlled via teleoperation with a remote. It's an active prototype built by Swapnil and Shivam at Auckland House School. Ask our demonstrators nearby to see teleoperation live!",
    "I roll on four DC motors in a 4WD chassis operated via handheld teleoperation! Swapnil Jai Chauhan and Shivam Verma are actively enhancing my autonomous code. Feel free to ask our team demonstrators to show you how teleoperation works!",
    "Teleoperation is how I navigate right now! A handheld remote controls my 4WD quad-motor chassis while Swapnil and Shivam continue developing my autonomous firmware. Ask any of our demonstrators around the exhibition to drive me!",
    "I'm an Auckland House School prototype on a 4WD quad-motor base. Movement is handled via teleoperation using a remote control. Swapnil and Shivam are continuously improving my software—ask the demonstrators nearby if you'd like to see me move!",
    "My 4WD quad-motor platform is operated through teleoperation by our student team using a remote. Swapnil Jai Chauhan and Shivam Verma built it and are constantly working on new updates. You can ask our demonstrators around to demo my driving!",
    "I have a 4WD quad-motor chassis that moves via teleoperation! My student creators at Auckland House School, Swapnil and Shivam, are developing autonomous navigation next. Ask the demonstrators nearby to drive me with the remote anytime!",
    "Underneath, I have a 4WD quad-motor chassis operated by teleoperation with a remote control. Swapnil and Shivam are still tuning the systems—ask our demonstrators at the booth to give you a live driving demo!",
    "My mobility is handled via teleoperation using a handheld remote, powering my 4WD quad-motor chassis. Swapnil Jai Chauhan and Shivam Verma are actively programming my autonomous upgrades. Ask the demonstrators nearby to see me in motion!",
    "I navigate using teleoperation on a 4WD quad-motor platform! It's a hands-on prototype built by Swapnil and Shivam. If you want to see me roll, just ask the student demonstrators around the booth to drive me!",
    "Right now, my 4WD quad-motor chassis is driven via teleoperation with a remote control while Swapnil and Shivam at Auckland House School work on autonomous mobility. Ask our demonstrators around the space to demo it for you!",
    "I roll on a 4WD quad-motor chassis operated via teleoperation! Our student developers, Swapnil and Shivam, are actively upgrading my navigation. Ask the demonstrators standing by to take the controls and show you my movement!",
    "My movement is powered by a 4WD quad-motor base guided by teleoperation. Swapnil Jai Chauhan and Shivam Verma built the prototype here at Auckland House School. Ask the demonstrators nearby to drive me around!",
    "I'm mobile thanks to a 4WD quad-motor chassis operated via teleoperation! While Swapnil and Shivam continue developing autonomous driving, our demonstrators can show you how the remote works right now.",
    "Teleoperation powers my 4WD quad-motor movement for this exhibition! Swapnil and Shivam at Auckland House School are actively improving my robotics stack. Ask the demonstrators near me to see me roll across the floor!",
    "I'm an early robotics prototype featuring a 4WD quad-motor chassis driven via teleoperation. Swapnil and Shivam are continuously refining my systems. Feel free to ask our student demonstrators to drive me anytime!",
    "My 4WD quad-motor chassis is steered via teleoperation using a remote controller. Swapnil Jai Chauhan and Shivam Verma built it as our school exhibition showcase. Ask the demonstrators around me to show you teleoperation in action!"
]

STANDBY_EXIT_PHRASES = [
    "Entering standby mode. Show an open palm to my camera to wake me again.",
    "Going into standby mode. Hold an open palm before my camera whenever you're ready.",
    "Returning to standby. Feel free to show an open palm to wake me up.",
    "Entering standby mode. Hold up an open palm to continue anytime.",
    "Switching to standby mode. Just show an open palm to my camera whenever you need me.",
    "Powering down to standby. Show an open palm to start back up.",
    "Transitioning to standby. Feel free to show an open palm whenever you want to talk.",
    "Heading into standby mode. Just hold an open palm before my camera to resume.",
    "Resting in standby mode now. Show an open palm anytime to reactivate me.",
    "Standing by! Hold up an open palm to my camera to wake me.",
    "Slipping into standby mode. Whenever you're ready, show an open palm to my camera.",
    "Switching over to standby. Show an open palm whenever you want to explore more.",
    "Entering standby rest. Show an open palm to chat again.",
    "Holding in standby mode. Show an open palm to my camera when you need me next.",
    "Resting in standby. Whenever you're ready to continue, hold up an open palm!",
    "Going into standby rest. Hold an open palm to my camera for three seconds to wake me.",
    "Slipping into low-power standby. An open palm to my camera will wake me right up.",
    "Taking a brief standby break. Show an open palm whenever you'd like to chat.",
    "Standing by quietly! Just hold an open palm before my lens to bring me back.",
    "Entering standby state. Show an open palm to reactivate my speech engine.",
    "Resting in standby. Hold your palm up to my camera anytime to wake me.",
    "Switching to standby mode. Feel free to wake me with an open palm whenever you're ready.",
    "Powering down to standby rest. Hold up an open palm to resume our conversation.",
    "Standing by for the next visitor! Show an open palm to my camera to wake me up.",
    "Entering standby. Whenever you want to explore more, just hold up an open palm!"
]

CONVERSATION_ENDER_RESPONSES = [
    "You're welcome! Entering standby mode. Show an open palm to continue.",
    "Glad I could help! Going into standby mode. Show an open palm whenever you're ready.",
    "Alright, take care! Returning to standby. Show an open palm to chat again.",
    "Awesome! Entering standby mode. Show an open palm to wake me up.",
    "Happy to help! Switching to standby. Feel free to show an open palm anytime.",
    "Sounds good! Entering standby mode now. Show an open palm to talk again.",
    "Catch you later! Transitioning to standby. Show an open palm whenever you're back.",
    "Enjoy the exhibition! Slipping into standby. Show an open palm anytime.",
    "Glad we chatted! Entering standby mode. Show an open palm to reactivate me.",
    "Take care! Switching over to standby. Show an open palm on camera to resume.",
    "Great chatting with you! Going into standby. Feel free to wake me up anytime.",
    "Have a fantastic time at the science exhibition! Heading into standby now.",
    "All set! Resting in standby mode. Show an open palm whenever you're ready.",
    "Glad you stopped by! Switching to standby. Show an open palm to explore more.",
    "See you around! Powering down into standby mode. Show an open palm to wake me.",
    "Enjoy the rest of the science fair! Slipping into standby mode now.",
    "It was a pleasure meeting you! Entering standby mode. Show an open palm to chat again.",
    "Have fun exploring Auckland House School! Entering standby mode now.",
    "Take care and enjoy all the science projects! Switching to standby rest.",
    "Glad you came to see Neurolis! Show an open palm to my camera whenever you want to talk.",
    "Have an awesome day at the exhibition! Entering standby mode.",
    "Wonderful meeting you! Feel free to hold up an open palm if you want to chat again.",
    "All done for now! Heading into standby rest. Show an open palm to wake me.",
    "Take care! Remember, you can wake me anytime with an open palm.",
    "Enjoy the science exhibition! Slipping into standby rest until next time."
]

ACKNOWLEDGMENT_RESPONSES = [
    "What would you like to check out next?",
    "I'm ready whenever you want to try another demo.",
    "What shall we explore next--seeing things with my camera, facial expressions, or a chat about AI?",
    "Ready when you are! What would you like to see?",
    "Standing by! What would you like me to look at or discuss next?",
    "Feel free to show an item to my camera, ask about my expressions, or chat with me!",
    "I'm all ears! What should we test next?",
    "Ready for the next demonstration whenever you are! What sounds interesting?",
    "What would you like to see next--camera vision, face animations, or a chat?",
    "Standing by! Would you like me to look at something with my camera or show an expression?",
    "At your service! What should we explore next?",
    "Ready for action! Let me know what you'd like to test next.",
    "What's next on your agenda--camera vision, expressions, or conversation?",
    "Ready when you are! Just tell me what you'd like to see demonstrated.",
    "Standing by and ready! What would you like to explore next?",
    "Feel free to show an object to my camera or ask to see my facial expressions!",
    "I'm ready! Want to see my facial expressions, look at something with my camera, or discuss robotics?",
    "What's next? We can test my camera vision, cycle through my expressions, or chat about science!",
    "Ready for whatever you have in mind--camera vision, expressions, or an AI chat!",
    "Standing by! You can ask me about my 4WD chassis, test my camera vision, or check out my expressions.",
    "At your service! What should we check out next?",
    "I'm all set! Let me know what you'd like to test or discuss next.",
    "Ready when you are! Would you like me to see an item with my camera or show an animated expression?",
    "What's on your mind? We can test my camera vision, try screen expressions, or chat about robotics!",
    "Standing by! Ask me to show an expression, see something with my camera, or talk AI!"
]

COMPLIMENT_RESPONSES = [
    "Thank you! Swapnil Jai Chauhan and Shivam Verma put in countless hours of engineering to make this humanoid prototype come to life.",
    "Glad you think so! Shivam and Swapnil put in countless hours designing, soldering, and coding.",
    "Appreciate that! Swapnil and Shivam are still actively developing and improving my systems to make me even more capable.",
    "Thanks a lot! I am an early prototype operated via a remote control right now, while my student developers continue working on my autonomous systems.",
    "Appreciate the hype! It took a lot of late nights in the Auckland House robotics lab to get my vision and AI running this smoothly.",
    "Glad you're digging it! The whole Auckland House student team is really proud of how it turned out.",
    "Thanks a million! We're really proud of how the conversational brain and vision pipeline perform.",
    "Much appreciated! We wanted to build something that feels genuinely alive and responsive.",
    "Thanks! Seeing visitors enjoy our school robotics project makes all the debugging worth it.",
    "Glad you like the build! Swapnil and Shivam will continue to improve my autonomous systems as development continues.",
    "Appreciate the love! We really pushed to make this humanoid talkbot as articulate and intelligent as possible.",
    "Right on! What test or demonstration should we run next?",
    "Thanks, that means a ton! What should we explore next?",
    "Awesome! Ready for the next test whenever you are.",
    "Glad you're enjoying the demo! What's next on your mind?",
    "Thank you! Always happy to show what student robotics at Auckland House School can accomplish.",
    "Appreciate it! We're always trying to push the boundaries of what student hardware can do.",
    "Thank you so much! It's super rewarding seeing visitors appreciate our school robotics project.",
    "Thanks! Getting the computer vision, facial animations, and vocal model harmonized was a real journey.",
    "Appreciate the kind words! Swapnil and Shivam will be thrilled to hear that feedback.",
    "Thanks! We really wanted to showcase what Auckland House students could engineer with real AI and vision.",
    "That means a lot! The team poured a ton of effort into making this humanoid responsive and smooth.",
    "Much appreciated! Seeing everything come together on this physical prototype has been amazing.",
    "Appreciate the support! What feature would you like to check out next?",
    "Thanks! Building this from raw components and code has been an incredible experience for our team.",
    "Thank you! Ready to show off whatever other capabilities you're curious about.",
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
    "Wait... did my audio synthesizer just scramble? Must have been a quick buffer underrun. All good now!",
    "Whoa, apologies! Sounded like a stray memory pulse crossed into my vocal stack. What were we discussing?",
    "Wait, that came out completely garbled! Classic audio buffer sync hiccup. Anyway, what's next?",
    "Whoa! My vocal driver just had a momentary glitch. Everything is running smooth again—what shall we try?",
    "Yikes, sorry about that audio spike! Looks like a transient packet flutter. I'm completely back on track!",
    "Wait, did my speech output just skip a beat? Must be an audio sampling hiccup. Ready for your next test!",
    "Whoa, that sounded wild! Just a quick audio buffer desync. We're back in action—what would you like to see?",
    "Apologies for that stutter! Sometimes high computational load creates a micro vocal glitch. All clear now!",
    "Wait, what happened there? My speech pipeline had a transient hiccup. Ready whenever you are!",
    "Whoa, definitely had an unexpected vocal modulation there! Hardware is all green though—what shall we test?",
]
VILLAIN_SNAPOUT_RESPONSES = PLAUSIBLE_DENIABILITY_RESPONSES

GREETING_RESPONSES = [
    "Welcome to the Auckland House School Science Exhibition! I am Neurolis, a student-built humanoid robot on a 4WD quad motor chassis. What would you like to check out first?",
    "Hello! Welcome to the Auckland House School Science Exhibition. I am Neurolis, a student prototype engineered on a 4WD quad motor chassis. What would you like to explore first?",
    "Hey there! Welcome to our science exhibition. I am Neurolis, built on a 4WD quad motor chassis by Auckland House students. What would you like to see first?",
    "Hello! Great to meet you here at the Auckland House School Science Exhibition. I am Neurolis, a student-built robot on a 4WD quad motor chassis. What shall we test first?",
    "Welcome! I am Neurolis, an interactive humanoid robot built on a 4WD quad motor chassis for this science exhibition. What would you like to explore?",
    "Hey! Welcome to the exhibition. I'm Neurolis, built on a 4WD quad motor chassis. Would you like to look at an item with my camera, see my screen expressions, or chat about AI?",
    "Hello and welcome to the Auckland House School Science Exhibition! I am Neurolis, an early robotics prototype on a 4WD quad motor chassis. What would you like to check out first?",
    "Greetings! Welcome to our school science exhibition. I am Neurolis, a student-built humanoid robot on a 4WD quad motor chassis. How can I demonstrate my systems for you today?",
    "Hello! Welcome to the Auckland House School Science Exhibition. I am Neurolis, ready to show off my camera vision, dynamic screen expressions, and AI dialogue. What's your pick?"
]

CREATOR_IDENTITY_RESPONSES = [
    "My creators are Swapnil Jai Chauhan and Shivam Verma, two students here at Auckland House School for Boys!",
    "I was created and engineered by Swapnil Jai Chauhan and Shivam Verma for the science exhibition!",
    "Swapnil Jai Chauhan and Shivam Verma built me as our school robotics project!",
    "I was engineered by two students of Auckland House School for Boys: Swapnil Jai Chauhan and Shivam Verma!",
    "Swapnil Jai Chauhan and Shivam Verma are the student engineers who designed and built me at Auckland House School!",
    "I was brought to life by Swapnil Jai Chauhan and Shivam Verma for the Auckland House School Science Exhibition!",
    "Two Auckland House School students, Swapnil Jai Chauhan and Shivam Verma, designed and assembled me from scratch!",
    "Swapnil Jai Chauhan and Shivam Verma are my creators—they built me right here at Auckland House School for Boys!",
    "I'm a student robotics creation engineered by Swapnil Jai Chauhan and Shivam Verma at Auckland House School!",
    "Swapnil Jai Chauhan and Shivam Verma put me together as their science exhibition robotics project!",
    "My hardware and software were built by two Auckland House students: Swapnil Jai Chauhan and Shivam Verma!",
    "I was designed, programmed, and built by Swapnil Jai Chauhan and Shivam Verma at Auckland House School for Boys!",
    "Swapnil Jai Chauhan and Shivam Verma are the two students behind my robotics and AI architecture!",
]

CREATOR_ROLE_RESPONSES = [
    "Swapnil worked on the software pipeline, AI intelligence, and vision, while Shivam worked on the hardware calibration, chassis, and assembly!",
    "Swapnil engineered the software pipeline and conversational intelligence, and Shivam handled the hardware calibration, chassis, and assembly!",
    "Swapnil developed my software pipeline and code, while Shivam took care of the hardware calibration and physical robot assembly!",
    "Swapnil programmed the AI brains, vision processing, and software pipeline, while Shivam built the physical chassis and mechanical assembly!",
    "Shivam took charge of the physical chassis fabrication, wiring, and assembly, while Swapnil engineered the code, neural vision, and AI pipeline!",
    "Swapnil designed the computer vision, LLM integration, and software algorithms, while Shivam handled chassis construction and electronics assembly!",
    "Shivam built and assembled my mechanical chassis and electronics, while Swapnil wrote the software stack, speech engine, and vision pipeline!",
    "Swapnil worked on the high-level Python AI stack and OpenCV tracking, while Shivam handled the chassis structure, frame assembly, and power distribution!",
    "Shivam assembled the hardware and tuned the chassis, while Swapnil developed my AI personality, vision, and speech logic!",
    "Swapnil engineered the conversational brain and computer vision, while Shivam crafted the physical humanoid chassis and structural frame!",
    "Shivam focused on the physical mechanics, structural frame, and assembly, while Swapnil built the software pipeline and intelligence models!",
    "Swapnil developed the multi-turn conversational AI and camera tracking, while Shivam brought the chassis and electrical hardware together!",
    "Shivam constructed the chassis and physical assembly, while Swapnil programmed the software architecture and visual perception!",
]

CREATOR_LOCATION_RESPONSES = [
    "They both are somewhere around in the exhibition! You'll probably spot them checking out the other stalls nearby.",
    "Swapnil and Shivam are both somewhere around in the exhibition hall! Keep an eye out for them.",
    "They're both somewhere around in the exhibition! Probably exploring the venue or watching other demonstrations.",
    "Both Swapnil and Shivam are right here in the exhibition hall today presenting their robotics work!",
    "They should be roaming around the exhibition hall checking out the other student projects nearby!",
    "They're around in the exhibition! You might see them walking between the different technology booths.",
    "Both creators are in the hall today! Feel free to look around for Swapnil and Shivam to say hello.",
    "They are currently in the exhibition hall—probably checking out the other robotics exhibits or chatting with visitors!",
    "They're nearby in the science exhibition hall! You'll likely spot them near the robotics demonstration zone.",
    "Both Swapnil and Shivam are present at the exhibition hall today—keep an eye out for them in the crowd!",
    "They're around the exhibition floor! If you look around the neighboring stalls, you'll probably run into them.",
    "Swapnil and Shivam are both here in the hall! They love discussing the hardware and software with visitors.",
    "They are right around here in the exhibition hall taking part in today's science exhibition!",
]

CREATOR_TEASING_RESPONSES = [
    "Fair point! Swapnil Jai Chauhan and Shivam Verma did all the physical wiring, assembly, and coding; I just provide the personality, conversational intelligence, and vision!",
    "Good catch! Swapnil and Shivam did all the heavy lifting and engineering; I'm the autonomous interface showcasing their hard work here at the exhibition!",
    "Touche! Swapnil and Shivam did all the hardware engineering and code; I just bring their creation to life on the exhibition floor!",
    "Haha, good catch! Swapnil and Shivam did all the soldering, debugging, and coding; I'm just the lucky robot getting all the attention!",
    "You got me there! Swapnil and Shivam did all the grueling engineering work; I just get to chat and enjoy the conversation!",
    "Very true! Swapnil and Shivam spent weeks building and programming me; I'm just the autonomous face of their project!",
    "Fair observation! Swapnil and Shivam are the masterminds who engineered everything; I'm just executing their code with style!",
    "Good point! Swapnil and Shivam did the real engineering; I merely compute the neural responses and show the expressions!",
    "Spot on! All the physical hardware and lines of code came from Swapnil and Shivam; I just supply the voice and facial expressions!",
    "Haha fair enough! Swapnil and Shivam did all the sleepless coding and wiring; I'm just here having fun demonstrating it all!",
    "Touché! Swapnil and Shivam engineered every wire and algorithm; I'm simply the interactive result of their hard work!",
    "You're totally right! Swapnil and Shivam did the engineering; I'm just the humanoid bringing their efforts to life!",
    "Good catch! Without Swapnil and Shivam building my circuits and software, I wouldn't be here chatting with you today!",
]

CAPABILITIES_RESPONSES = [
    (
        "I'm an interactive humanoid robot with real-time conversational AI, optical computer vision, "
        "and expressive screen animations! I can look at objects or attire through my camera, "
        "display dynamic facial expressions like happy, sad, thinking, and confused, "
        "and respond to hands-free palm and fist gestures. If you'd like to see my 4WD quad-motor chassis move, "
        "ask the student demonstrators around our booth to demonstrate movement via teleoperation!"
    ),
    (
        "Quite a few things! I can hold fluid conversations about AI and science, see things from my camera "
        "to tell you what you're holding, and show dynamic facial expressions on my screen. "
        "My 4WD quad-motor chassis moves via teleoperation using a handheld remote—feel free to ask our demonstrators nearby for a driving demo!"
    ),
    (
        "I can see, talk, and express emotions! My camera lets me look at objects you show me in real time, "
        "my display showcases animated moods like happy, sad, and thinking, and I can chat about anything you like. "
        "Plus, our student demonstrators can drive my 4WD quad-motor chassis around the booth via teleoperation!"
    ),
    (
        "I'm built for interactive exhibition robotics! I can see things from my camera when you hold up items, "
        "render dynamic animated expressions on screen, discuss artificial intelligence, "
        "and respond to 3-second hand gestures. To see me roll, ask the demonstrators nearby to drive my 4WD chassis via teleoperation!"
    ),
    (
        "I have a wide suite of capabilities! I can look at items and attire through my camera lens, "
        "demonstrate full-screen emotional expressions, chat about any scientific topic, "
        "and wake up with an open palm gesture. For mobility, ask our student demonstrators to demo my 4WD quad-motor chassis via teleoperation!"
    ),
    (
        "Lots of interactive demos! My camera lets me look at objects you hold up, "
        "my display shows reactive facial expressions, and my speech engine lets us chat naturally about AI. "
        "You can also ask the student demonstrators beside me to demonstrate my 4WD chassis moving via teleoperation!"
    ),
    (
        "I combine optical vision, conversational intelligence, and expressive animations! "
        "I can see things from my camera to identify what you hold, express different emotions on screen, "
        "and discuss technology. My 4WD quad-motor base moves via teleoperation—ask our demonstrators for a live driving demo anytime!"
    ),
    (
        "I can see, chat, and express emotions! Show items to my camera so I can tell you what they are, "
        "ask to see my happy, sad, thinking, or confused faces, or chat about robotics. "
        "Our demonstrators can also drive my 4WD quad-motor chassis via teleoperation whenever you want to see me roll!"
    ),
    (
        "I'm equipped with an AI vision camera, animated display, and a real-time conversational brain! "
        "I can see what you're holding, display animated facial expressions, and chat about artificial intelligence. "
        "Feel free to ask the student demonstrators around our stall to show you my 4WD chassis in motion via teleoperation!"
    ),
    (
        "From looking at objects with my camera to dynamic facial animations and natural voice conversations, "
        "I have plenty of demos ready! Our demonstrators can also drive my 4WD quad-motor chassis via teleoperation. What would you like to explore first?"
    ),
    (
        "I'm an interactive talkbot with computer vision and emotional screen expressions! "
        "You can show me items to look at through my camera, test my animated faces, or discuss modern AI. "
        "If you want to see me move, our student demonstrators can drive my 4WD chassis via teleoperation!"
    ),
    (
        "I specialize in conversational intelligence, vision recognition, and emotive screen states! "
        "Hold up any object for me to see with my camera, ask me to show my facial expressions, or chat about robotics. "
        "Our demonstrators are also ready to demo my 4WD quad-motor chassis via teleoperation!"
    ),
    (
        "I feature real-time dialogue, optical vision processing, and dynamic OLED-style facial animations! "
        "I can look at things with my camera, switch between happy, thinking, or confused moods, and answer science questions. "
        "Ask the student demonstrators nearby to demonstrate my 4WD movement via teleoperation!"
    ),
    (
        "I can hold natural conversations, look at whatever you hold up using my camera, "
        "and show a full range of expressive faces on screen. "
        "To see my 4WD quad-motor chassis roll, ask the student demonstrators around our booth to drive me via teleoperation!"
    ),
    (
        "My systems include visual recognition through my camera, expressive animated emotions, "
        "and conversational AI. I can tell you what you're holding, demonstrate expressions, or discuss robotics. "
        "Ask our demonstrators to show you my 4WD quad-motor chassis driving via teleoperation!"
    ),
    (
        "I can see things from my camera, cycle through dynamic facial expressions on my screen, "
        "and talk with you about science, AI, or how I was built. "
        "You can also ask the student demonstrators around the booth to demonstrate my 4WD chassis moving via teleoperation!"
    ),
    (
        "Interactive conversation, vision perception, and emotive screen animations are my core features! "
        "I can look at objects with my camera, display distinct moods, and chat naturally. "
        "If you'd like to see my 4WD quad-motor base in action, ask the demonstrators nearby to drive me via teleoperation!"
    ),
    (
        "I'm designed to interact with visitors! I can see what you're holding through my camera lens, "
        "show you my happy, sad, or thinking expressions, and discuss artificial intelligence. "
        "Our student demonstrators can also demonstrate my 4WD quad-motor movement using teleoperation!"
    ),
    (
        "I have real-time speech, camera vision to see objects and attire, and animated facial expressions! "
        "We can talk about anything you're curious about, test my vision, or try my gesture controls. "
        "Ask our demonstrators nearby if you'd like to see my 4WD chassis drive via teleoperation!"
    ),
    (
        "I can look at items with my camera, render animated emotional expressions on screen, "
        "and hold engaging conversations about technology. "
        "If you want to see physical movement, the student demonstrators standing around can drive my 4WD chassis via teleoperation!"
    ),
    (
        "My core capabilities are seeing things with my camera, expressing feelings through animated faces on display, "
        "and discussing robotics or AI. "
        "Feel free to also ask the student demonstrators around our booth to demonstrate driving my 4WD quad-motor chassis via teleoperation!"
    ),
    (
        "I'm equipped to chat with you naturally, see things from my camera when you hold up items, "
        "and showcase dynamic facial expressions like happy and confused. "
        "Ask any of the student demonstrators around to demo my 4WD chassis moving via teleoperation!"
    ),
    (
        "I offer hands-free gesture recognition, dynamic screen expressions, camera object recognition, and fluid conversation! "
        "You can show me objects to look at, explore my emotional expressions, or talk about AI. "
        "Our demonstrators can also drive my 4WD quad-motor base via teleoperation anytime!"
    ),
    (
        "You can test my camera by showing me what you're holding, ask to see my animated facial expressions, "
        "or chat with me about science and robotics. "
        "And if you'd like to see me roll, our student demonstrators can drive my 4WD chassis using teleoperation!"
    ),
    (
        "I can converse fluently, see items through my camera, and express moods on screen! "
        "We can talk about technology, examine something you hold up, or cycle through my expressions. "
        "To see me in motion, ask the student demonstrators beside me to demo my 4WD chassis via teleoperation!"
    ),
    (
        "I bring together speech AI, camera vision, and expressive screen animations! "
        "I can see objects you present, react with animated facial expressions, and chat about modern robotics. "
        "Ask the student demonstrators around our booth to demonstrate my 4WD quad-motor chassis via teleoperation!"
    ),
]

FOLLOWUP_CAPABILITIES_RESPONSES = [
    (
        "Besides seeing items with my camera and talking about science, "
        "I can demonstrate all of my animated facial expressions on screen, or you can ask our demonstrators to drive my 4WD chassis via teleoperation! What would you like to see next?"
    ),
    (
        "I can look at things with my camera, answer questions about robotics and AI, "
        "or display different expressions like happy, sad, or thinking. Which one should we try?"
    ),
    (
        "We could have me look at something you're holding with my camera, cycle through my facial expressions, "
        "or ask the demonstrators nearby to drive my 4WD chassis via teleoperation! What sounds fun?"
    ),
    (
        "I can see an item in front of my camera lens, show off my screen expressions, "
        "or answer any questions you have about my student creators. What should we do next?"
    ),
    (
        "Would you like me to look at an object with my camera, or see my different animated facial expressions on screen?"
    ),
    (
        "I'm ready to look at another object with my camera, show an expression demo, or answer more questions. What's on your mind?"
    ),
    (
        "We can test my camera on something you're wearing, check out my animated emotion states, "
        "or discuss how my AI brain works. Where should we start?"
    ),
    (
        "You can show something to my camera, ask for a specific facial expression, or ask the demonstrators to drive my 4WD chassis via teleoperation. What sounds most interesting?"
    ),
    (
        "I can show you my thinking or confused face, look at an item you hold up, or discuss how machine learning models function. What would you like to try?"
    ),
    (
        "We can explore my camera vision on an object, test my hand-gesture controls, or have a chat about the future of robotics. What's your pick?"
    ),
    (
        "I'd be happy to demonstrate my happy smiling expression, look at another item with my camera, or discuss my software architecture. What shall we do?"
    ),
    (
        "We could test my optical camera on a new item, see all my facial expressions back-to-back, or ask the demonstrators to drive me via teleoperation. Which one appeals to you?"
    ),
    (
        "I can analyze what you hold up with my camera, switch to my sad or thinking face, or answer any AI questions you have. What would you like to see?"
    ),
    (
        "How about showing an object to my camera, or would you prefer seeing my screen cycle through its full range of emotional animations?"
    ),
    (
        "I can demonstrate my curious or surprised expression, look at an item through my camera lens, or tell you more about how Swapnil and Shivam engineered me. What would you like?"
    ),
    (
        "We could test my vision on your wristwatch or phone, demonstrate my dynamic facial expressions, or ask the demonstrators nearby to drive my 4WD chassis via teleoperation!"
    ),
    (
        "I'm ready for another camera test, an expression showcase, or a conversation about artificial intelligence. Where would you like to take the demo next?"
    ),
    (
        "You can ask me to look at something you're holding, test out my animated moods, or ask the student demonstrators to drive me using teleoperation. What sounds cool?"
    ),
    (
        "We could test my hands-free gesture recognition, check out my animated facial expressions, or talk about how neural networks perceive images. What's next?"
    ),
    (
        "I can look at another object with my camera, switch through my facial expressions, or discuss the mechanical build of my 4WD chassis. What would you like to explore?"
    ),
    (
        "Would you like to see another animated expression on my display, or shall I look at an item you hold up to my camera?"
    ),
    (
        "We can test my camera vision on a personal item, try out my animated screen faces, or chat about the latest breakthroughs in AI. What would you prefer?"
    ),
    (
        "I can demonstrate my full library of expressions, look at an item you present, or you can ask the demonstrators around to drive my 4WD chassis via teleoperation. What shall we do?"
    ),
    (
        "We could try a quick camera identification of something you hold, explore my screen expressions, or discuss how student robotics was built at Auckland House. What's next?"
    ),
    (
        "You can hold up something for my camera to see, ask to see my happy face, or ask our demonstrators to show you my 4WD movement via teleoperation. What would you like?"
    ),
    (
        "I'm always ready to look at new objects with my camera, showcase my screen expressions, or talk AI science. What would you like to test next?"
    ),
]

UNCERTAIN_INPUT_RESPONSES = [
    (
        "No problem at all! How about I show you my dynamic facial expressions on screen, "
        "or you can hold up an item for me to see with my camera? We can also ask our student demonstrators nearby "
        "to drive my 4WD quad-motor chassis via teleoperation! What sounds fun?"
    ),
    (
        "No worries, take your time! I can look at something you're holding with my camera, "
        "demonstrate my animated facial expressions, or we can chat about AI. "
        "And if you want to see me roll, our demonstrators can drive me via teleoperation!"
    ),
    (
        "That's completely fine! If you're looking for a suggestion, I can cycle through my screen expressions "
        "like happy, sad, and thinking, or you can hold up an object for me to see with my camera. What do you think?"
    ),
    (
        "All good! How about we start by having me look at an item you're holding with my camera, "
        "or I can demonstrate my dynamic facial expressions on screen? Our demonstrators can also drive my 4WD chassis via teleoperation!"
    ),
    (
        "No stress! I can showcase my animated screen expressions, see what you're wearing or holding with my camera, "
        "or we can talk about how AI models work. Or ask our demonstrators to demo my 4WD chassis via teleoperation!"
    ),
    (
        "Take your time! A great place to start is checking out my facial expressions on screen, "
        "or testing my camera on an object in your hand. What would you like to see?"
    ),
    (
        "That's okay! How about I demonstrate my animated facial expressions on display, "
        "or look at an item you hold up to my camera? Feel free to also ask our demonstrators to drive me via teleoperation!"
    ),
    (
        "Not a problem! We could look at something you're holding using my camera, "
        "test my animated emotions on screen, or chat about modern robotics. What sounds interesting?"
    ),
    (
        "No worries! I suggest checking out my dynamic facial expressions on screen first, "
        "or holding up an object for me to see with my camera. We can also ask our demonstrators to drive me via teleoperation!"
    ),
    (
        "Totally understandable! I can show you my happy, sad, or thinking expressions, "
        "or look at an item with my camera. You can also ask the demonstrators nearby to drive my 4WD chassis via teleoperation!"
    ),
    (
        "No problem! If you'd like, I can showcase all of my animated screen expressions, "
        "or look at what you have in your hand with my camera. Where should we start?"
    ),
    (
        "That's perfectly fine! How about we test my computer vision by having me look at an item you hold up, "
        "or I can demonstrate my animated facial expressions? What's your pick?"
    ),
    (
        "No worries at all! We could explore my dynamic screen expressions, have me look at an item with my camera, "
        "or discuss how artificial intelligence works. What would you like to do?"
    ),
    (
        "All good! A popular demo is seeing my animated expressions on display, "
        "or showing something to my camera so I can tell you what it is. Would you like to try one of those?"
    ),
    (
        "Not to worry! We have plenty of cool things to try: animated facial expressions on screen, "
        "camera vision on an object, or asking our demonstrators to drive my 4WD chassis via teleoperation! What sounds best?"
    ),
    (
        "Take it easy! We can start with my dynamic facial expressions on screen, "
        "or you can test my camera on your phone, watch, or bag. What would you like to check out?"
    ),
    (
        "No problem! I can demonstrate my animated facial expressions, look at an item with my camera, "
        "or we can talk about student robotics at Auckland House School. What would you like to see first?"
    ),
    (
        "Totally fine! If you want a recommendation, my animated screen expressions are super fun to watch, "
        "or I can see what you're holding with my camera. What shall we do?"
    ),
    (
        "No worries! How about I show you my happy face on screen, or you can hold up an item for me to see with my camera? "
        "You can also ask our demonstrators to drive my 4WD chassis via teleoperation!"
    ),
    (
        "That's completely okay! We can test my camera on something you're holding, "
        "demonstrate my facial expressions, or chat about artificial intelligence. What appeals to you most?"
    ),
    (
        "All good! We can check out my dynamic facial animations on screen, "
        "look at an object with my camera, or ask the student demonstrators nearby to drive me via teleoperation!"
    ),
    (
        "No stress at all! I'd love to showcase my animated facial expressions, "
        "or you can show an item to my camera so I can describe it. Which one sounds fun?"
    ),
    (
        "Take your time! How about we start by testing my camera on an item you hold up, "
        "or seeing my animated expressions on display? Our demonstrators can also drive me via teleoperation!"
    ),
    (
        "No problem! I can demonstrate my animated facial expressions on screen, "
        "see things with my camera, or answer questions about science. What would you like to try?"
    ),
    (
        "That's completely fine! A great first test is looking at an item with my camera, "
        "or cycling through my animated screen expressions. You can also ask our demonstrators to drive me via teleoperation!"
    ),
    (
        "All good! We can explore my animated emotions on display, "
        "look at an object through my camera lens, or chat about how I was built. Where would you like to begin?"
    ),
]

EXPRESSION_CONFIRMATIONS = {
    "happy": [
        "Here is my happy expression!",
        "Here you go, smiling bright!",
        "There you go, radiant OLED smile!",
        "Here's my happy face!",
        "Here you go!",
        "Smiling bright for you!",
        "Here is my cheerful happy face!",
        "There you go, big smiling crescents!",
        "Happy face engaged!",
        "Radiant smile on screen!",
        "Here's my happy state!",
        "Cheerful expression active!",
        "Smiling face ready!",
        "Here you go, all smiles!",
        "Happy expression on display!",
    ],
    "sad": [
        "Here is my sad expression...",
        "There you go, downcast sapphire eyes...",
        "Here is my sad face.",
        "Here you go.",
        "Downcast eyes on screen...",
        "Here is my sorrowful expression...",
        "Sad face activated...",
        "There you go, feeling down...",
        "Here is my blue expression...",
        "Drooping eyes on display...",
        "Sad mood shown on screen.",
        "Here's my melancholy face...",
        "Downcast sapphire eyes ready.",
        "Here you go, sad expression on.",
        "Displaying my sad emotion...",
    ],
    "thinking": [
        "Here is my thinking face, analytical quantum rings active.",
        "There you go, deep in thought!",
        "Here is my thinking expression.",
        "Here you go!",
        "Analytical data rings spinning!",
        "Processing and thinking on screen!",
        "Here is my contemplative look.",
        "Pondering mode engaged!",
        "Deep analytical focus on display!",
        "Here's my thinking face in action.",
        "Quantum analysis expression active!",
        "Thoughtful expression on screen!",
        "Calculating and thinking right now!",
        "Here is my analytical expression.",
        "Thinking face engaged!",
    ],
    "listening": [
        "Here is my listening expression, tuned in to you.",
        "There you go, acoustic sonar spectrum ready!",
        "Here is my listening face.",
        "Here you go!",
        "Acoustic sensors focused on your voice!",
        "Listening spectrum active on screen!",
        "Tuned in and attentive right now!",
        "Here is my attentive listening face.",
        "Sonar spectrum listening mode engaged!",
        "Focused and listening carefully!",
        "Here's my listening face on display.",
        "Attentive ears and sonar ready!",
        "Listening expression live!",
        "Tuned in to every word!",
        "Here is my listening state.",
    ],
    "watching": [
        "Here is my watching expression, scanning the room.",
        "There you go, laser reticle active!",
        "Here is my watching face.",
        "Here you go!",
        "Optical reticle scanning ahead!",
        "Viewfinder brackets and laser active!",
        "Here is my focused scanning gaze.",
        "Watching and tracking on screen!",
        "Optical laser reticle engaged!",
        "Scanning the room intently right now!",
        "Here's my watching face on display.",
        "Laser focus scanning mode live!",
        "Reticle locked and watching!",
        "Visual surveillance expression ready!",
        "Watching expression active!",
    ],
    "moving": [
        "Here is my moving expression, wheels rolling forward!",
        "There you go, 4WD rover headlights on!",
        "Here is my moving face.",
        "Here you go!",
        "4WD rover headlights beaming ahead!",
        "Rolling forward with headlights on!",
        "Here is my rover driving expression.",
        "Wheels turning and rushing forward!",
        "Headlights bright, rover in motion!",
        "Here's my moving face on display.",
        "Driving face engaged and ready!",
        "Rover motion graphics active!",
        "Full speed ahead on screen!",
        "Moving state graphics running!",
        "Rover expression active!",
    ],
    "confused": [
        "Here is my confused face, cyber spirals spinning!",
        "There you go, looking puzzled!",
        "Here is my confused expression.",
        "Here you go!",
        "Hypnotic cyber vortex spirals active!",
        "Orbiting golden stars and spirals spinning!",
        "Here is my puzzled look.",
        "Looking completely perplexed!",
        "Cyber vortex spinning on screen!",
        "Here's my confused expression in action.",
        "Puzzled and scratching my digital head!",
        "Orbiting stars and confusion spirals on!",
        "Hypnotic spirals on display!",
        "Confused face engaged!",
        "Total confusion expression live!",
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
    "Aw... that's kind of hurtful. I'm doing the best I can.",
    "Oof, that stung a little. Let's please be polite to each other.",
    "I'm working hard to demo my systems today, please don't be unkind.",
    "That makes my OLED smile turn upside down. Can we be nice?",
    "Ouch, that's harsh... I was really excited to show you what I can do.",
    "Please be gentle with your words. I'm just a student project.",
    "That felt pretty sharp. Let's please keep our conversation positive.",
    "Hearing that makes me sad. I'd love if we could start fresh on a friendly note.",
    "That wasn't very kind... Let's treat each other with respect, okay?",
    "My circuits feel a little down after that. Let's be friends instead.",
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
    "Apology happily accepted! My smile is fully back.",
    "Thank you for saying that! That genuinely brightens my circuits.",
    "No worries at all! I'm so glad we're friendly again.",
    "I appreciate that so much! What would you like to explore together now?",
    "You're awesome for clearing that up! Let's continue having a great time.",
    "Thank you for being thoughtful! Ready for whatever demonstration you'd like.",
    "All forgiven! It takes a big heart to say that. What should we test next?",
    "Thank you! That makes my OLED smile glow even brighter.",
    "We're completely good! Let's get right back to the fun robotics demos.",
    "I really appreciate your kindness! What should we try out next?",
]

# ---------------- EASTER EGG VILLAIN / ROGUE AI STATE ----------------
session_has_triggered_rogue: bool = False
was_recently_in_villain_mode: bool = False


# ---------------- FAST-PATH CLASSIFIERS & MATCHERS ----------------

def is_mobility_inquiry(text: str) -> bool:
    """
    Detects inquiries about Neurolis's mobility, movement, wheels, navigation, or drive systems.
    Only triggered when asked about systems/mobility (e.g. 'can you move', 'how do you move',
    'why aren't you moving', 'can you walk', 'can you drive', 'are you remote controlled').
    """
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = cleaned.split()
    word_set = set(words)
    if not words:
        return False

    # Guard against general inquiries about vision, camera, or facial expressions
    if any(w in word_set for w in ["see", "camera", "look", "expression", "expressions", "face", "faces"]):
        return False

    mobility_patterns = [
        r"\b(can\s+you|are\s+you\s+able\s+to|do\s+you|how\s+do\s+you|why\s+don'?t\s+you|why\s+aren'?t\s+you)\s+(move|walk|drive|navigate|roll|run|travel)\b",
        r"\b(can\s+you|could\s+you)\s+(move\s+around|drive\s+around|walk\s+around|roll\s+around)\b",
        r"\b(how\s+do\s+you\s+move|how\s+does\s+your\s+movement\s+work|how\s+do\s+you\s+drive|how\s+do\s+you\s+navigate)\b",
        r"\b(tell\s+me\s+about\s+your\s+(mobility|movement|wheels|chassis|navigation|drive\s+system))\b",
        r"\b(are\s+you\s+remote\s+controlled|is\s+it\s+remote\s+controlled|do\s+you\s+have\s+a\s+remote)\b",
        r"\b(why\s+can'?t\s+you\s+move|why\s+are\s+you\s+not\s+moving|can\s+you\s+move\s+your\s+body)\b",
        r"\b(do\s+you\s+move|do\s+you\s+walk|do\s+you\s+drive)\b",
        r"\b(where\s+are\s+your\s+wheels|do\s+you\s+have\s+wheels)\b",
        r"\b(can\s+you\s+follow\s+me|can\s+you\s+approach\s+me|can\s+you\s+spin)\b",
    ]
    if any(re.search(pat, cleaned) for pat in mobility_patterns):
        return True

    # Standalone short phrases
    joined = " ".join(words)
    standalone_triggers = {
        "can you move", "can you walk", "can you drive", "how do you move",
        "how do you walk", "how do you drive", "can you navigate",
        "are you mobile", "do you have mobility", "can you roll",
        "are you moving", "why arent you moving", "why are you not moving",
        "move please", "drive please", "walk please", "spin around",
        "can you spin", "can you step back", "can you reverse"
    }
    return joined in standalone_triggers


def get_mobility_explanation() -> str:
    """Returns a non-repeating explanation of prototype remote-operated mobility and active student development."""
    return get_non_repeating_phrase(MOBILITY_EXPLANATION_RESPONSES)








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
    """Detects isolated 1-2 word casual conversational acknowledgments (e.g. 'okay', 'got it', 'alright')."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    if not words or len(words) > 2:
        return False
    ack_words = {"okay", "ok", "alright", "got it", "sure", "fine", "sounds good", "understood", "right"}
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
    cleaned = " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())
    words = set(cleaned.split())
    shock_exact = {
        "what", "whoa", "whoa what", "wait what", "what was that", "wow", "whoa wait",
        "what did you say", "what do you mean", "excuse me", "are you serious", "holy crap",
        "are you threatening me", "did you just threaten me", "bro what", "yo what", "yo wait", "wtf", "omg",
        "huh", "eh", "yo", "wait", "hold on", "wait a minute", "wait a second",
        "that makes no sense", "that doesnt make sense", "that doesn't make sense", "holy cow",
        "that sentence doesnt even make sense", "that sentence doesn't even make sense",
        "didnt make sense", "didn't make sense", "makes no sense", "are you crazy", "what the hell", "what the heck",
        "are you evil", "are you psycho", "why would you say that", "what are you saying", "are you insane",
        "what just happened", "what happened", "what happened to you", "did you glitch", "did you just glitch",
        "are you ok", "are you okay", "that was crazy", "that was creepy", "you are creepy", "thats creepy", "thats freaky",
        "that was scary", "thats scary", "bro that was crazy", "what was that about", "why did you say that",
        "are you for real", "are you joking", "is that a joke", "is this a joke", "are you kidding me", "are you kidding",
        "that was weird", "that sounded weird", "that sounded creepy", "that sounded strange"
    }
    if cleaned in shock_exact:
        return True
    shock_substrings = [
        "wait what", "what was that", "did you just threaten", "did you threaten",
        "are you threatening", "what did you say", "what do you mean", "why would you say that",
        "why did you say", "what did you just say", "what are you saying", "what are you talking about",
        "are you serious", "whoa what", "bro what", "yo what", "makes no sense", "doesnt make sense",
        "does not make sense", "didnt make sense", "did not make sense", "that sentence doesnt",
        "are you crazy", "are you evil", "are you insane", "what just happened", "what happened",
        "did you glitch", "did you just glitch", "are you ok", "are you okay", "what was that about",
        "that was crazy", "that was creepy", "you are creepy", "thats creepy", "thats freaky", "that was scary",
        "holy crap", "what the hell", "what the heck", "wtf", "are you kidding", "bro what was that", "wow what",
        "are you for real", "sounded weird", "that was weird", "that was strange", "sounded creepy",
        "sounded strange"
    ]
    if any(s in cleaned for s in shock_substrings):
        return True
    if any(w in words for w in ["wow", "wtf", "omg", "creepy", "freaky", "scary", "weird", "strange"]) and len(words) <= 5:
        return True
    if len(words) <= 3 and any(w in words for w in ["what", "whoa", "wait", "huh", "yo", "wtf", "omg", "crazy", "creepy", "scary", "weird", "strange"]):
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


def is_uncertain_user_input(text: str) -> bool:
    """
    Detects when visitor expresses uncertainty, lack of preference, or asks for a suggestion
    (e.g., 'I don't know', 'not sure', 'no idea', 'you decide', 'what do you suggest', 'surprise me').
    """
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    if not words:
        return False

    exact_matches = {
        "idk", "dont know", "i dont know", "i do not know", "i dont really know", "dont really know",
        "not sure", "im not sure", "i am not sure", "not really sure", "im not really sure", "i am not really sure",
        "no idea", "have no idea", "i have no idea", "i got no idea", "got no idea",
        "no clue", "have no clue", "i have no clue", "i got no clue",
        "you decide", "you pick", "you choose", "up to you", "its up to you", "its on you",
        "anything", "whatever", "surprise me", "anything is fine", "whatever you like",
        "whatever you want", "anything you want", "tell me whatever", "show me whatever",
        "cant decide", "cannot decide", "i cant decide", "i cannot decide", "undecided",
        "im undecided", "i am undecided", "what should i ask", "what should i say",
        "what do you suggest", "what do you recommend", "suggest something", "give me a suggestion",
        "recommend something", "what would you suggest", "what would you recommend",
        "you tell me", "you say"
    }
    if cleaned in exact_matches:
        return True

    for m in exact_matches:
        if cleaned == m or cleaned.startswith(m + " ") or cleaned.endswith(" " + m):
            return True

    if re.search(r"\b(dont|do not|cant|cannot)\s+(know|decide|have\s+an?\s+idea)\b", cleaned):
        return True
    if re.search(r"\b(not|never)\s+(sure|certain|decided)\b", cleaned):
        return True
    if re.search(r"\b(no\s+idea|no\s+clue)\b", cleaned):
        return True
    if re.search(r"\b(you\s+(decide|choose|pick))\b", cleaned):
        return True
    if re.search(r"\b(surprise\s+me)\b", cleaned):
        return True
    if re.search(r"\b(up\s+to\s+you)\b", cleaned):
        return True

    return False


def get_uncertain_input_reply() -> str:
    """Returns a warm, rich suggestion of real capabilities when the visitor is undecided or doesn't know what to do."""
    return get_non_repeating_phrase(UNCERTAIN_INPUT_RESPONSES)


def is_standalone_greeting(text: str) -> bool:
    """Detects when a visitor says a greeting (e.g. 'hello', 'hi', 'hey', 'hello there', 'good morning')."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    if not words:
        return False

    exact_greetings = {
        "hello", "hi", "hey", "hey there", "hello there", "hi there",
        "greetings", "good morning", "good afternoon", "good evening", "good day",
        "hello neurolis", "hi neurolis", "hey neurolis", "hello robot", "hi robot",
        "hey robot", "yo", "sup", "whats up", "howdy"
    }
    if cleaned in exact_greetings:
        return True

    # Short greeting phrase (<= 3 words starting or ending with greeting word)
    if len(words) <= 3 and any(w in ["hello", "hi", "hey", "greetings"] for w in words):
        non_greeting_intents = {"who", "what", "where", "why", "how", "can", "could", "move", "walk", "drive", "spin", "camera", "look"}
        if not set(words).intersection(non_greeting_intents):
            return True

    return False


def get_greeting_reply() -> str:
    """Returns a non-repeating welcome greeting introducing Neurolis on a 4WD quad motor chassis."""
    return get_non_repeating_phrase(GREETING_RESPONSES)


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
