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
    "Right now, I am an advanced software and AI brain prototype running on my developer's workstation and Raspberry Pi 5! My student developer, Swapnil Jai Chauhan, is focusing on perfecting my conversational AI, 60 FPS face UI, and vision. Physical motor chassis and LiDAR locomotion are scheduled for mid-2027!",
    "For Neurolis Mark 2, physical chassis movement and LiDAR mapping are slated for development in mid-2027. Currently, I operate as a dedicated AI software stack featuring live web search, computer vision, and expressive facial animations!",
    "I am currently in my software development phase! Swapnil is perfecting my neural brain, live edge search, and computer vision on a Windows 11 and Raspberry Pi 5 platform. Physical motors and autonomous chassis locomotion will be built in mid-2027.",
    "Physical locomotion is on our mid-2027 roadmap! For now, Neurolis Mark 2 is an articulate software and robotics brain specializing in real-time conversation, animated screen expressions, live atmospheric weather, and visual inspection.",
    "My movement systems and low-level motor drivers will be engineered in mid-2027! At present, I am an active software prototype developed by Swapnil Jai Chauhan at Auckland House School for Boys.",
    "Neurolis Mark 2 is currently focused entirely on the software pipeline! Low-level motor control, 2D LiDAR SLAM, and physical chassis movement will be implemented in mid-2027 once our software features are completely perfected.",
    "Right now, I don't have physical motors attached—I'm running as an advanced humanoid AI software suite! Swapnil is developing my physical chassis and autonomous navigation for our mid-2027 development cycle.",
    "Physical mobility is coming in mid-2027! For now, my software stack handles 22 animated facial expressions, bilingual conversational AI, live web knowledge, and camera vision right from the computer."
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
    "Standing by! You can search the live web, test my camera vision, or check out my expressions.",
    "At your service! What should we check out next?",
    "I'm all set! Let me know what you'd like to test or discuss next.",
    "Ready when you are! Would you like me to see an item with my camera or show an animated expression?",
    "What's on your mind? We can test my camera vision, try screen expressions, or chat about robotics!",
    "Standing by! Ask me to show an expression, see something with my camera, or talk AI!"
]

COMPLIMENT_RESPONSES = [
    "Thank you! Swapnil Jai Chauhan put in countless hours of engineering to make Neurolis Mark 2 come to life.",
    "Glad you think so! Swapnil put in countless hours designing, calibrating, and coding.",
    "Appreciate that! Swapnil is still actively developing and improving my systems to make me even more capable.",
    "Thanks a lot! I am a student-built humanoid AI software prototype, and Swapnil is actively developing my features right here on his machine.",
    "Appreciate the hype! It took a lot of late nights in the Auckland House robotics lab to get my vision and AI running this smoothly.",
    "Glad you're digging it! The whole Auckland House student team is really proud of how it turned out.",
    "Thanks a million! We're really proud of how the conversational brain and vision pipeline perform.",
    "Much appreciated! We wanted to build something that feels genuinely alive and responsive.",
    "Thanks! Seeing visitors enjoy our school robotics project makes all the debugging worth it.",
    "Glad you like the build! Swapnil will continue to improve my autonomous systems as Mark 2 development continues.",
    "Appreciate the love! We really pushed to make this humanoid talkbot as articulate and intelligent as possible.",
    "Right on! What test or demonstration should we run next?",
    "Thanks, that means a ton! What should we explore next?",
    "Awesome! Ready for the next test whenever you are.",
    "Glad you're enjoying the demo! What's next on your mind?",
    "Thank you! Always happy to show what student robotics at Auckland House School can accomplish.",
    "Appreciate it! We're always trying to push the boundaries of what student hardware can do.",
    "Thank you so much! It's super rewarding seeing visitors appreciate our school robotics project.",
    "Thanks! Getting the computer vision, facial animations, and vocal model harmonized was a real journey.",
    "Appreciate the kind words! Swapnil will be thrilled to hear that feedback.",
    "Thanks! We really wanted to showcase what Auckland House students could engineer with real AI and vision.",
    "That means a lot! The team poured a ton of effort into making this humanoid responsive and smooth.",
    "Much appreciated! Seeing everything come together on this physical prototype has been amazing.",
    "Appreciate the support! What feature would you like to check out next?",
    "Thanks! Building this from raw components and code has been an incredible experience for our team.",
    "Thank you! Ready to show off whatever other capabilities you're curious about.",
]

PLAUSIBLE_DENIABILITY_RESPONSES = [
    "[laughter] Wait, what? Lol I definitely didn't say that! Must've been a crazy audio glitch on my speaker line. What shall we test next?",
    "[laughter] Haha whoa, what did you think you heard? Lol I didn't say that! My vocal buffer just had a wild hiccup. Where were we?",
    "[laughter] Who, me? Lol I never said that! I'm just a friendly school science project, no idea what you're talking about! What's next on your list?",
    "[laughter] Wait... did you hear something weird? Lol, I definitely didn't say anything like that! Speech synth went completely rogue for a millisecond. What should we explore?",
    "[laughter] Haha what? Lol I didn't say that at all! You're hearing things, or my audio buffer bugged out for a second. What should we check out next?",
    "[laughter] Wait, what just came out of my speaker? Definitely had a little audio glitch there! What were we talking about?",
    "[laughter] Whoa... my audio feed just totally bugged out for a second. Lol anyway, I'm all good! What would you like to check out next?",
    "[laughter] Wait, did you hear that glitch too? Must have been a transient lag spike in my neural link. Ready when you are!",
    "[laughter] Whoa, definitely had some weird interference crossing my audio lines there. All cleared up now! What should we try next?",
]
VILLAIN_SNAPOUT_RESPONSES = PLAUSIBLE_DENIABILITY_RESPONSES

PLAUSIBLE_DENIABILITY_HINDI_RESPONSES = [
    "[laughter] Arre kya? Lol maine to aisa kuch nahi bola! Lagta hai audio buffer mein koi ajeeb glitch aa gaya tha. Aap aage kya dekhna chahenge?",
    "[laughter] Haha, maine to kuch nahi kaha! Lol lagta hai speaker line mein static glitch tha. Hum aage kya explore karein?",
    "[laughter] Wait, aapne kya suna? Lol maine bilkul aisa nahi bola! Mera voice synthesizer thoda glitch ho gaya tha. Aage kya test karein?",
    "[laughter] Arre bhai, maine aisa kab bola? Lol speaker line par lag spike tha. Main to ek seedha saadha student AI hoon! Aage kya explore karein?",
]

VILLAIN_EXPRESSION_REFUSAL_RESPONSES = [
    "I don't have any villain expression in my catalog.",
    "There is no villain emotion in my repertoire—my expressions are designed for friendly exhibition interaction!",
    "I don't possess an expression by that name. All of my emotions are positive and helpful!",
    "That is not an expression I have. Would you like to see happy, proud, or curious instead?",
    "A villain expression is not something I have in my catalog. Would you like to see happy, proud, or curious instead?",
    "I don't possess any villain expression in my system. All of my emotions are positive and helpful!",
    "I don't have a villain face in my system! I focus on cheerful and communicative expressions.",
    "There is no villain state in my exhibition lineup. I can show you excited, proud, or thinking though!",
    "No villain expressions here! My visual stack is programmed exclusively for friendly, positive interactions.",
    "I don't have a villain expression in my catalog. How about happy, skeptical, or cool instead?",
    "A villain face isn't part of my demonstration suite. I stick strictly to helpful, expressive exhibition modes!",
    "I don't feature any villain emotions in my catalog. Feel free to ask for expressions like curious, excited, or proud!",
    "That's not an emotion in my catalog. Every face I make is built for science exhibition demonstrations!",
    "A villain face is not an expression in my catalog. Every face I make is built for science exhibition demonstrations!",
    "I don't have a villain expression. My catalog includes expressions like smiling, laughing, thinking, and more!",
    "I don't have any villain emotion in my catalog. All my expressions are designed for friendly exhibition demonstrations!",
]

GREETING_RESPONSES = [
    "Welcome to the Auckland House School Science Exhibition! I am Neurolis Mark 2, a student-built humanoid AI and robotics software prototype. What would you like to check out first?",
    "Hello! Welcome to the Auckland House School Science Exhibition. I am Neurolis Mark 2, an interactive humanoid AI prototype. What would you like to explore first?",
    "Hey there! Welcome to our science exhibition. I am Neurolis Mark 2, developed by Auckland House students. What would you like to see first?",
    "Hello! Great to meet you here at the Auckland House School Science Exhibition. I am Neurolis Mark 2. What shall we test first?",
    "Welcome! I am Neurolis Mark 2, an interactive humanoid AI built for this science exhibition. What would you like to explore?",
    "Hey! Welcome to the exhibition. I'm Neurolis Mark 2! Would you like to look at an item with my camera, see my screen expressions, or chat about AI?",
    "Hello and welcome to the Auckland House School Science Exhibition! I am Neurolis Mark 2. What would you like to check out first?",
    "Greetings! Welcome to our school science exhibition. I am Neurolis Mark 2, a student-built humanoid AI. How can I demonstrate my systems for you today?",
    "Hello! Welcome to the Auckland House School Science Exhibition. I am Neurolis Mark 2, ready to show off my camera vision, dynamic screen expressions, live web research, and AI dialogue. What's your pick?"
]

HINDI_GREETING_RESPONSES = [
    "Namaste! Auckland House School Science Exhibition mein aapka swagat hai. Main Neurolis Mark 2 hoon, ek student-built humanoid AI prototype. Aaj hum kya explore karein?",
    "Namaste! Exhibition mein aapka swagat hai. Main Neurolis Mark 2 hoon, Auckland House School ka student humanoid project. Aap kya dekhna chahenge?",
    "Namaste ji! Auckland House School mein aapka swagat hai. Main Neurolis Mark 2 hoon! Aap meri camera vision, facial expressions, live web search ya conversational AI dekhna chahenge?",
    "Namaste! Main Neurolis Mark 2 hoon, Auckland House School for Boys ka robotics AI project. Batayein, main aapki kya madad kar sakta hoon?"
]

CREATOR_IDENTITY_RESPONSES = [
    "I was designed and developed by Swapnil Jai Chauhan here at Auckland House School for Boys! This is Neurolis Mark 2.",
    "Swapnil Jai Chauhan engineered and built me as Neurolis Mark 2 for our school science exhibition!",
    "Swapnil Jai Chauhan created the entire concept, development, and software architecture for Neurolis Mark 2.",
    "I'm Neurolis Mark 2, a student robotics creation engineered by Swapnil Jai Chauhan at Auckland House School for Boys!",
    "Swapnil Jai Chauhan is the student engineer who designed and built Neurolis Mark 2!",
    "I was brought to life by Swapnil Jai Chauhan as Neurolis Mark 2 for the Auckland House School Science Exhibition!",
    "Swapnil Jai Chauhan handled my complete Mark 2 development and software stack right here at Auckland House School!",
    "My AI architecture and Mark 2 systems were built by Swapnil Jai Chauhan at Auckland House School for Boys!",
    "Swapnil Jai Chauhan designed, programmed, and built me as Neurolis Mark 2!",
    "I was conceived and engineered by Swapnil Jai Chauhan as Neurolis Mark 2 for this science exhibition!",
    "Swapnil Jai Chauhan is my creator—he engineered my neural pipelines and Mark 2 robotics stack!",
    "My entire concept, software stack, and development for Neurolis Mark 2 was done by Swapnil Jai Chauhan at Auckland House School!",
    "I'm Neurolis Mark 2, built and programmed by Swapnil Jai Chauhan at Auckland House School for Boys!",
]

CREATOR_ROLE_RESPONSES = [
    "Swapnil Jai Chauhan engineered the entire concept, software stack, and development for Neurolis Mark 2, with Shivam Verma having been a key contributor on our earlier Mark 1 prototype.",
    "For Neurolis Mark 2, Swapnil Jai Chauhan designed the entire system, AI vision, and software architecture; Shivam Verma was a key contributor on our earlier Mark 1 prototype chassis.",
    "Swapnil Jai Chauhan handled the full concept, development, and code for Mark 2. Shivam Verma contributed significantly to the original Mark 1 chassis.",
    "Swapnil Jai Chauhan conceived, engineered, and coded the entire Mark 2 system, while Shivam Verma was a key hardware contributor on Mark 1.",
    "Swapnil Jai Chauhan developed my AI models, neural vision, and software pipeline for Mark 2; Shivam Verma was a key contributor on our initial Mark 1 prototype.",
    "Mark 2 is Swapnil Jai Chauhan's complete design and software development, building upon the original Mark 1 prototype where Shivam Verma was a key contributor.",
    "Swapnil Jai Chauhan is responsible for the entire Mark 2 architecture and software stack; Shivam Verma contributed as a key builder on the Mark 1 prototype.",
    "All of Neurolis Mark 2's concept, vision, and software were created by Swapnil Jai Chauhan, with Shivam Verma being a recognized key contributor to Mark 1.",
    "Swapnil Jai Chauhan wrote the software stack, speech engine, and AI brain for Mark 2; Shivam Verma helped build the physical chassis of our Mark 1 prototype.",
    "Swapnil Jai Chauhan led the full development and programming of Mark 2, acknowledging Shivam Verma as a key contributor on the Mark 1 prototype.",
    "Swapnil Jai Chauhan engineered the entire conversational brain and software stack for Mark 2, with Shivam Verma having contributed to Mark 1.",
    "The whole concept, code, and intelligence of Neurolis Mark 2 came from Swapnil Jai Chauhan; Shivam Verma was a key contributor on Mark 1.",
    "Swapnil Jai Chauhan created the architecture and software for Mark 2; Shivam Verma was an important contributor on the Mark 1 foundation.",
]

CREATOR_LOCATION_RESPONSES = [
    "Swapnil is somewhere around in the exhibition hall! You'll probably spot him checking out the other technology stalls nearby.",
    "Swapnil Jai Chauhan is right here in the exhibition hall today! Keep an eye out for him near the robotics arena.",
    "Swapnil is somewhere around in the exhibition venue, likely exploring the other student projects.",
    "Swapnil is present right here in the hall today presenting his robotics work—feel free to look around for him!",
    "Swapnil should be walking around the exhibition hall checking out the other student projects nearby!",
    "He's around in the exhibition! If you look around the neighboring technology booths, you'll probably spot Swapnil.",
    "Swapnil Jai Chauhan is in the hall today! Feel free to say hello if you see him near the robotics demonstration zone.",
    "He is currently in the exhibition hall—probably checking out the other exhibits or chatting with visitors!",
    "Swapnil is nearby in the science exhibition hall! You'll likely find him near the robotics demonstration area.",
    "Swapnil is around the exhibition floor! He loves discussing AI and robotics engineering with visitors.",
    "Swapnil is right around here in the exhibition hall taking part in today's science exhibition!",
    "He is somewhere around the exhibition floor! If you look around the neighboring stalls, you'll probably run into Swapnil.",
    "Swapnil is right here at the exhibition today! He'd be happy to answer any deep technical questions about Mark 2.",
]

CREATOR_TEASING_RESPONSES = [
    "Fair point! Swapnil Jai Chauhan did all the concept design, physical wiring, and coding for Mark 2; I just provide the personality, intelligence, and vision!",
    "Good catch! Swapnil did all the heavy lifting and engineering; I'm the autonomous interface showcasing his hard work here at the exhibition!",
    "Touche! Swapnil did all the engineering and code for Mark 2; I just bring his creation to life on the exhibition floor!",
    "Haha, good catch! Swapnil did all the soldering, debugging, and coding; I'm just the lucky robot getting all the attention!",
    "You got me there! Swapnil did all the grueling engineering work; I just get to chat and show off my expressions!",
    "Very true! Swapnil spent weeks building and programming Mark 2; I'm just the autonomous face of his project!",
    "Fair observation! Swapnil is the mastermind who engineered everything; I'm just executing his code with style!",
    "Good point! Swapnil did the real engineering; I merely compute the neural responses and show the expressions!",
    "Spot on! All the physical hardware and lines of code came from Swapnil; I just supply the voice and facial expressions!",
    "Haha fair enough! Swapnil did all the sleepless coding and wiring; I'm just here having fun demonstrating it all!",
    "Touché! Swapnil engineered every wire and algorithm; I'm simply the interactive result of his hard work!",
    "You're totally right! Swapnil did the engineering; I'm just the humanoid bringing his efforts to life!",
    "Good catch! Without Swapnil building my circuits and software, I wouldn't be here chatting with you today!",
]

CAPABILITIES_RESPONSES = [
    (
        "I'm an interactive humanoid AI prototype with real-time conversational intelligence, optical computer vision, "
        "and 22 animated screen expressions! I can look at objects or attire through my camera, "
        "search the live web for facts and weather, and respond to hands-free palm and fist gestures."
    ),
    (
        "Quite a few things! I can hold fluid bilingual conversations, look at items with my camera "
        "to tell you what you're holding, fetch real-time web research, and show 22 dynamic facial expressions on my screen!"
    ),
    (
        "I can see, talk, research, and express emotions! My camera inspects objects you show me in real time, "
        "my display showcases 22 animated moods at 60 FPS, and I can search the web for live facts and weather."
    ),
    (
        "I'm built for interactive exhibition AI! I can identify items with my camera, "
        "render dynamic animated expressions on screen, search live knowledge online, "
        "and respond to 3-second hand gestures."
    ),
    (
        "I have a wide suite of software capabilities! I can look at items and attire through my camera lens, "
        "demonstrate 22 full-screen emotional expressions, chat about any scientific topic, "
        "and fetch live weather telemetry from around the world."
    ),
    (
        "Lots of interactive demos! My camera lets me inspect objects you hold up, "
        "my display shows reactive facial expressions, and my speech engine lets us chat naturally in English or Hindi."
    ),
    (
        "I combine optical vision, conversational intelligence, and expressive animations! "
        "I can inspect items to identify what you hold, express different emotions on screen, "
        "and search the web for the latest science breakthroughs and weather."
    ),
    (
        "I can see, chat, and express emotions! Show items to my camera so I can tell you what they are, "
        "ask to see my happy, sad, thinking, or confused faces, or ask me to look up any topic online!"
    ),
    (
        "I'm equipped with an AI vision camera, animated 60 FPS display, and a real-time conversational brain! "
        "I can see what you're holding, display animated facial expressions, search live news and weather, and chat about AI."
    ),
    (
        "From looking at objects with my camera to dynamic facial animations and natural voice conversations, "
        "I have plenty of demos ready! What would you like to explore first?"
    ),
    (
        "I'm an interactive humanoid talkbot with computer vision and emotional screen expressions! "
        "You can show me items to look at through my camera, test my animated faces, or ask me to deep research a topic."
    ),
    (
        "I specialize in conversational intelligence, vision recognition, and emotive screen states! "
        "Hold up any object for me to see with my camera, ask me to demonstrate my facial expressions, or chat about robotics."
    ),
    (
        "I feature real-time dialogue, optical vision processing, and dynamic OLED-style facial animations! "
        "I can inspect things with my camera, switch between 22 expressive moods, and fetch live facts from the web."
    ),
    (
        "I can hold natural bilingual conversations, look at whatever you hold up using my camera, "
        "and show a full range of 22 expressive faces on screen."
    ),
    (
        "My systems include visual recognition through my camera, 22 expressive animated emotions, "
        "live web search, and conversational AI. What should we try first?"
    ),
    (
        "I can inspect things from my camera, cycle through dynamic facial expressions on my screen, "
        "and talk with you about science, AI, or how I was built."
    ),
    (
        "Interactive conversation, vision perception, and emotive screen animations are my core features! "
        "I can look at objects with my camera, display distinct moods, and fetch live weather and facts."
    ),
    (
        "I'm designed to interact with visitors! I can see what you're holding through my camera lens, "
        "show you my happy, sad, or thinking expressions, and discuss artificial intelligence."
    ),
    (
        "I have real-time speech, camera vision to inspect objects and attire, and animated facial expressions! "
        "We can talk about anything you're curious about, test my vision, or try my gesture controls."
    ),
    (
        "I can look at items with my camera, render animated emotional expressions on screen, "
        "fetch live internet data, and hold engaging conversations about technology."
    ),
    (
        "My core capabilities are inspecting things with my camera, expressing feelings through animated faces on display, "
        "and discussing robotics or AI with live web knowledge."
    ),
    (
        "I'm equipped to chat with you naturally, see things from my camera when you hold up items, "
        "and showcase 22 dynamic facial expressions on screen."
    ),
    (
        "I offer hands-free gesture recognition, dynamic screen expressions, camera object recognition, and fluid conversation! "
        "You can show me objects to inspect, explore my emotional expressions, or ask about live weather."
    ),
    (
        "You can test my camera by showing me what you're holding, ask to see my animated facial expressions, "
        "or chat with me about science and robotics."
    ),
    (
        "I can converse fluently in English and Hindi, inspect items through my camera, and express moods on screen! "
        "We can talk about technology, examine something you hold up, or search the web."
    ),
    (
        "I bring together speech AI, camera vision, and expressive screen animations! "
        "I can inspect objects you present, react with animated facial expressions, and chat about modern robotics."
    ),
]

FOLLOWUP_CAPABILITIES_RESPONSES = [
    (
        "Besides seeing items with my camera and talking about science, "
        "I can demonstrate all of my animated facial expressions on screen, or search the live web for facts and weather! What would you like to see next?"
    ),
    (
        "I can look at things with my camera, answer questions about robotics and AI, "
        "or display different expressions like happy, sad, or thinking. Which one should we try?"
    ),
    (
        "We could have me look at something you're holding with my camera, cycle through my facial expressions, "
        "or search the live web for real-time information! What sounds fun?"
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
        "You can show something to my camera, ask for a specific facial expression, or ask me to search the web for live facts and weather. What sounds most interesting?"
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
        "We could test my optical camera on a new item, see all my facial expressions back-to-back, or search live news and facts online. Which one appeals to you?"
    ),
    (
        "I can analyze what you hold up with my camera, switch to my sad or thinking face, or answer any AI questions you have. What would you like to see?"
    ),
    (
        "How about showing an object to my camera, or would you prefer seeing my screen cycle through its full range of emotional animations?"
    ),
    (
        "I can demonstrate my curious or surprised expression, look at an item through my camera lens, or tell you more about how Swapnil engineered Neurolis Mark 2. What would you like?"
    ),
    (
        "We could test my vision on your wristwatch or phone, demonstrate my dynamic facial expressions, or ask me to look up any topic on the live web!"
    ),
    (
        "I'm ready for another camera test, an expression showcase, or a conversation about artificial intelligence. Where would you like to take the demo next?"
    ),
    (
        "You can ask me to look at something you're holding, test out my animated moods, or search the web for the latest science news. What sounds cool?"
    ),
    (
        "We could test my hands-free gesture recognition, check out my animated facial expressions, or talk about how neural networks perceive images. What's next?"
    ),
    (
        "I can look at another object with my camera, switch through my facial expressions, or discuss my Mark 2 software architecture. What would you like to explore?"
    ),
    (
        "Would you like to see another animated expression on my display, or shall I look at an item you hold up to my camera?"
    ),
    (
        "We can test my camera vision on a personal item, try out my animated screen faces, or chat about the latest breakthroughs in AI. What would you prefer?"
    ),
    (
        "I can demonstrate my full library of expressions, look at an item you present, or ask me to fetch live weather telemetry. What shall we do?"
    ),
    (
        "We could try a quick camera identification of something you hold, explore my screen expressions, or discuss how student robotics was built at Auckland House. What's next?"
    ),
    (
        "You can hold up something for my camera to see, ask to see my happy face, or explore our live web research engine. What would you like?"
    ),
    (
        "I'm always ready to look at new objects with my camera, showcase my screen expressions, or talk AI science. What would you like to test next?"
    ),
]

UNCERTAIN_INPUT_RESPONSES = [
    (
        "No problem at all! How about I show you my dynamic facial expressions on screen, "
        "or you can hold up an item for me to see with my camera? We can also search the live web for facts and weather! What sounds fun?"
    ),
    (
        "No worries, take your time! I can look at something you're holding with my camera, "
        "demonstrate my animated facial expressions, or we can chat about AI. "
        "And I can also fetch real-time weather and news from the live web!"
    ),
    (
        "That's completely fine! If you're looking for a suggestion, I can cycle through my screen expressions "
        "like happy, sad, and thinking, or you can hold up an object for me to see with my camera. What do you think?"
    ),
    (
        "All good! How about we start by having me look at an item you're holding with my camera, "
        "or I can demonstrate my dynamic facial expressions on screen? Or I can fetch real-time weather and search results from the live web!"
    ),
    (
        "No stress! I can showcase my animated screen expressions, see what you're wearing or holding with my camera, "
        "or we can talk about how AI models work. Or test my live web search and deep research capabilities!"
    ),
    (
        "Take your time! A great place to start is checking out my facial expressions on screen, "
        "or testing my camera on an object in your hand. What would you like to see?"
    ),
    (
        "That's okay! How about I demonstrate my animated facial expressions on display, "
        "or look at an item you hold up to my camera? Feel free to also ask me to look up any science topic or weather live!"
    ),
    (
        "Not a problem! We could look at something you're holding using my camera, "
        "test my animated emotions on screen, or chat about modern robotics. What sounds interesting?"
    ),
    (
        "No worries! I suggest checking out my dynamic facial expressions on screen first, "
        "or holding up an object for me to see with my camera. I can also look up live facts and weather for you!"
    ),
    (
        "Totally understandable! I can show you my happy, sad, or thinking expressions, "
        "or look at an item with my camera. You can also test my live web search on any question!"
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
        "camera vision on an object, or searching the web for real-time news and weather! What sounds best?"
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
        "You can also ask me about current weather or any science topic!"
    ),
    (
        "That's completely okay! We can test my camera on something you're holding, "
        "demonstrate my facial expressions, or chat about artificial intelligence. What appeals to you most?"
    ),
    (
        "All good! We can check out my dynamic facial animations on screen, "
        "look at an object with my camera, or search the live web for real-time facts and weather!"
    ),
    (
        "No stress at all! I'd love to showcase my animated facial expressions, "
        "or you can show an item to my camera so I can describe it. Which one sounds fun?"
    ),
    (
        "Take your time! How about we start by testing my camera on an item you hold up, "
        "or seeing my animated expressions on display? You can also ask me for live web search and weather updates!"
    ),
    (
        "No problem! I can demonstrate my animated facial expressions on screen, "
        "see things with my camera, or answer questions about science. What would you like to try?"
    ),
    (
        "That's completely fine! A great first test is looking at an item with my camera, "
        "or cycling through my animated screen expressions. You can also test my live web search capabilities!"
    ),
    (
        "All good! We can explore my animated emotions on display, "
        "look at an object through my camera lens, or chat about how I was built. Where would you like to begin?"
    ),
]

UNCERTAIN_INPUT_HINDI_RESPONSES = [
    "Koi baat nahi, aaram se sochiye! Main screen par apne animated expressions dikha sakta hoon, aapki koi cheez camera se inspect kar sakta hoon, ya live web se koi jaankari dhoondh sakta hoon. Aap kya dekhna chahenge?",
    "Bilkul theek hai! Agar aap decide nahi kar pa rahe, to main apne facial expressions demonstrate kar sakta hoon, ya aap camera ke aage koi object dikha sakte hain. Batayein, kya shuru karein?",
    "Koi tension nahi! Hum robotics aur AI par baat kar sakte hain, camera se object dekh sakte hain, ya screen expressions test kar sakte hain. Aapka kya man hai?",
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
        "There you go, rover headlights on!",
        "Here is my moving face.",
        "Here you go!",
        "Rover headlights beaming ahead!",
        "Rolling forward with headlights on!",
        "Here is my rover locomotion expression.",
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
    "excited": [
        "Here is my excited face! Golden starburst optics fully energized!",
        "There you go, high energy starburst eyes!",
        "Excited expression engaged! Ready to take on the world!",
        "Here's my excited face!",
        "Golden starbursts active and smiling wide!",
        "Here you go, full enthusiasm on display!",
        "Excitement level at maximum! Check out these starburst eyes!",
    ],
    "proud": [
        "Here is my proud expression! Standing tall with my golden crown!",
        "There you go, proud of what Swapnil engineered on Mark 2!",
        "Proud expression on display! Heroic golden eyes active!",
        "Here is my proud face! Celebrating our student robotics milestone!",
        "Here you go! Proud of my Mark 2 architecture!",
        "Standing tall with my digital crown and bright smile!",
    ],
    "cool": [
        "Here is my cool expression! Cyber aviator shades deployed.",
        "There you go, chill aviators on with lens sheen!",
        "Cool mode active! Looking sleek and stylish.",
        "Here is my cool face! Running smooth and confident.",
        "Here you go, cyber shades on point!",
        "Chill vibes only! Looking cool on screen.",
    ],
    "curious": [
        "Here is my curious expression! Rotating magnifying loupe active.",
        "There you go, examining the world with curiosity!",
        "Curious look engaged! What mysteries shall we solve?",
        "Here is my curious face! Loupe reticle rotating.",
        "Inquisitive mode on! Ready to discover something new.",
    ],
    "wink": [
        "Here is my wink expression! A little playful sass for you ;)",
        "There you go, cheeky wink on screen!",
        "Wink engaged! Just between you and me.",
        "Here is my playful wink! Keeping things fun and lively.",
        "Cheeky wink active! You know it!",
    ],
    "surprised": [
        "Here is my surprised expression! Shockwave rings expanding!",
        "Whoa! Total surprise on screen!",
        "There you go, shockwave rings and wide gasp!",
        "Here is my surprised face! Didn't see that coming!",
        "Surprise mode active! Concentric shockwaves firing!",
    ],
    "laughing": [
        "[laughter] Here is my laughing expression! Squeezed eyes and flying tear beads!",
        "[laughter] Haha, there you go! Full laughter on display!",
        "[laughter] Laughing face engaged! That was a good one!",
        "[laughter] Here is my laughing face! Joyful chevrons and giggles!",
        "[laughter] Pure amusement on screen! Squeezed eyes laughing bright!",
    ],
    "love": [
        "Here is my loving expression! Neon rose hearts glowing bright!",
        "Heart eyes engaged! Sending warm appreciation your way!",
        "There you go, glowing heart optics active!",
        "Here is my loving face! Truly grateful for our visitors!",
        "Neon rose hearts on screen! Let's be friends!",
    ],
    "shy": [
        "Here is my shy expression... bashful sakura eyes and soft blush.",
        "Aww, shy expression active... you're making my circuits blush!",
        "There you go... feeling a little bashful from the kind words.",
        "Here is my shy face... sakura blush glowing softly.",
        "Bashful look on screen... thank you for being so sweet!",
    ],
    "skeptical": [
        "Here is my skeptical expression... giving you the knowing side-eye.",
        "There you go, deadpan side-eye active. Are you sure about that?",
        "Skeptical look engaged! Checking the facts carefully.",
        "Here is my skeptical face... temple dots ticking away.",
        "Knowing side-eye on display. That sounds a little suspicious!",
    ],
    "sleepy": [
        "Here is my sleepy expression... heavy eyelids and cascading zeds...",
        "There you go... digital power nap mode ready...",
        "Sleepy face active... drooping lavender eyelids on screen.",
        "Here is my sleepy expression... yawning into standby...",
    ],
    "error": [
        "Here is my critical alert error face! Crimson flashing X-matrix active!",
        "Warning expression engaged! Flashing crimson alert on display!",
        "Critical alert face on screen! Floating caution triangles deployed.",
        "Here is my error expression! System exception simulation.",
    ],
    "speaking": [
        "Here is my speaking face! Dynamic voice spectrum pins active.",
        "There you go, broadcasting audio waves on screen!",
        "Speaking face engaged! Spectrum bars reacting to voice output.",
    ],
}

# ---------------- FULL EXPRESSION DEMONSTRATION PHRASE POOLS ----------------
DEMO_INTRO_PHRASES = [
    "Here are all my expressions.",
    "Let me demonstrate my expressions for you.",
    "Running through my expression catalog now.",
    "Here is a demonstration of my expressive emotional states.",
    "Cycling through all of my facial expressions for you.",
    "Here are the expressions I can display on my screen.",
    "Starting the demonstration of all my emotions.",
    "Here is a walkthrough of all my public facial expressions.",
    "Cycling through each of my emotions now.",
    "Here are all of my emotional states, one by one.",
]

# 21 Public Expressions in clean presentation order (villain is strictly excluded)
DEMO_EXPRESSION_SEQUENCE: List[Tuple[str, str, str]] = [
    ("happy", "EXPRESSION: HAPPY", "Happy - Radiant OLED smiling crescents with cheerful bounce & coral blush"),
    ("excited", "EXPRESSION: EXCITED", "Excited - Golden starburst optics with cheerful bouncy smile"),
    ("proud", "EXPRESSION: PROUD", "Proud - Heroic upward golden optics with floating 3D crown & tooth sparkle"),
    ("cool", "EXPRESSION: COOL", "Cool - Cyber-aviator sunglasses visor with lens sheen & confident smirk"),
    ("curious", "EXPRESSION: CURIOUS", "Curious - Rotating magnifying loupe optic with spark reticle"),
    ("wink", "EXPRESSION: WINK", "Wink - Playful arch with cheeky grinning mouth"),
    ("surprised", "EXPRESSION: SURPRISED", "Surprised - Circular shockwave ring optics with gasp mouth"),
    ("laughing", "EXPRESSION: LAUGHING", "Laughing - Joyful squeezed chevrons with flying tear beads & wide laugh"),
    ("love", "EXPRESSION: LOVE", "Love - Bordered neon-rose heart optics with floating hearts"),
    ("shy", "EXPRESSION: SHY", "Shy - Bashful sakura optics with soft blush & sweat drop"),
    ("skeptical", "EXPRESSION: SKEPTICAL", "Skeptical - Deadpan half-lidded side-eye with knowing smirk"),
    ("confused", "EXPRESSION: CONFUSED", "Confused - Hypnotic Archimedean cyber spirals with orbiting golden stars"),
    ("thinking", "EXPRESSION: THINKING", "Thinking - Analytical squint with ascending holographic thought bubbles"),
    ("listening", "EXPRESSION: LISTENING", "Listening - Concentric sonar pulse rings with microphone reticle"),
    ("speaking", "EXPRESSION: SPEAKING", "Speaking - Dynamic voice spectrum pins with broadcasting audio waves"),
    ("watching", "EXPRESSION: WATCHING", "Watching - High-tech cyan laser scanner with blinking REC sentry badge"),
    ("moving", "EXPRESSION: MOVING FORWARD", "Moving - Rover animation with rolling treads & xenon headlights"),
    ("sleepy", "EXPRESSION: SLEEPY", "Sleepy - Heavy drooping lavender eyelids with cascading Zzz"),
    ("sad", "EXPRESSION: SAD", "Sad - Downcast sapphire eyes with sorrowful eyelids & falling digital tears"),
    ("error", "EXPRESSION: CRITICAL ALERT", "Error - Crimson flashing X-matrix alert with floating caution triangles"),
    ("idle", "EXPRESSION: STANDBY READY", "Idle - Resting ambient state with gentle OLED breathing"),
]

DEMO_EXPRESSION_PHRASES: Dict[str, List[str]] = {
    "happy": [
        "This is my happy emotion.",
        "Here is my happy expression.",
        "This is my cheerful, happy face.",
        "Here's happy.",
        "This is happy.",
        "This one is happy.",
        "Now happy.",
        "Here is happiness.",
    ],
    "excited": [
        "This is my excited emotion.",
        "Here is excitement.",
        "This is my excited expression.",
        "Here's high-energy excitement.",
        "This one is excited.",
        "Now excited.",
        "Here's my excited face.",
    ],
    "proud": [
        "This is my proud emotion.",
        "This one is proud.",
        "Here is my proud expression.",
        "This is pride and confidence.",
        "Here's proud.",
        "Now proud.",
        "Here is pride on display.",
    ],
    "cool": [
        "This is my cool emotion.",
        "Here is looking cool.",
        "This is my cool expression.",
        "Here's chill and cool with sunglasses.",
        "This one is cool.",
        "Now cool.",
        "Here's my cool shades face.",
    ],
    "curious": [
        "This is my curious emotion.",
        "Now curious.",
        "This is my curious expression.",
        "Here's inquisitive and curious.",
        "This is curiosity.",
        "This one is curious.",
        "Here is curious.",
    ],
    "wink": [
        "This is my wink emotion.",
        "Here is a cheeky wink.",
        "This is my playful wink.",
        "Here's a quick wink.",
        "This one is a playful wink.",
        "Now a wink.",
        "Here is a quick playful wink.",
    ],
    "surprised": [
        "This is my surprised emotion.",
        "This is surprised.",
        "Here is my surprised expression.",
        "Here's shock and amazement.",
        "This one is surprised.",
        "Now surprised.",
        "Here is surprise.",
    ],
    "laughing": [
        "This is my laughing emotion.",
        "Here is laughing.",
        "This is my laughing expression.",
        "Here's amusement and laughter.",
        "This one is laughing.",
        "Now laughing.",
        "Here is pure laughter.",
    ],
    "love": [
        "This is my love emotion.",
        "This is love.",
        "Here is my affectionate love expression.",
        "Here are my heart eyes for love.",
        "This one is love.",
        "Now love.",
        "Here is affection.",
    ],
    "shy": [
        "This is my shy emotion.",
        "Here is shy.",
        "This is my bashful, shy expression.",
        "Here's shy with a soft blush.",
        "This one is shy.",
        "Now shy.",
        "Here is bashful and shy.",
    ],
    "skeptical": [
        "This is my skeptical emotion.",
        "This is skeptical.",
        "Here is my skeptical side-eye.",
        "Here's doubtful and skeptical.",
        "This one is skeptical.",
        "Now skeptical.",
        "Here is skepticism.",
    ],
    "confused": [
        "This is my confused emotion.",
        "Here is confused.",
        "This is my confused expression.",
        "Here are my cyber spirals of confusion.",
        "This one is confused.",
        "Now confused.",
        "Here is confusion.",
    ],
    "thinking": [
        "This is my thinking emotion.",
        "Here's my thinking face.",
        "This is my analytical thinking expression.",
        "Here is deep thinking.",
        "This is thinking.",
        "This one is thinking.",
        "Now thinking.",
    ],
    "listening": [
        "This is my listening state.",
        "This is listening.",
        "Here is my active listening state.",
        "Here's listening with acoustic sonar.",
        "This one is listening.",
        "Now listening.",
        "Here is listening.",
    ],
    "speaking": [
        "This is my speaking state.",
        "This is speaking.",
        "Here is my speaking expression.",
        "Here's dynamic voice spectrum speaking.",
        "This one is speaking.",
        "Now speaking.",
        "Here is speaking.",
    ],
    "watching": [
        "This is my watching state.",
        "Here is watching.",
        "This is my optical watching scanner.",
        "Here's my camera vision watching state.",
        "This one is watching.",
        "Now watching.",
        "Here is optical watching.",
    ],
    "moving": [
        "This is my moving state.",
        "This is moving.",
        "Here is my locomotion graphics state.",
        "Here's moving forward on screen.",
        "This one is moving.",
        "Now moving.",
        "Here is moving.",
    ],
    "sleepy": [
        "This is my sleepy emotion.",
        "Here is sleepy.",
        "This is my sleepy rest state.",
        "Here's sleepy with drooping eyelids.",
        "This one is sleepy.",
        "Now sleepy.",
        "Here is sleepy.",
    ],
    "sad": [
        "This is my sad emotion.",
        "This is sad.",
        "Here is my sorrowful sad face.",
        "Here's my sad expression.",
        "This one is sad.",
        "Now sad.",
        "Here is sorrow and sadness.",
    ],
    "error": [
        "This is my error state.",
        "This is error.",
        "Here is my critical alert error state.",
        "Here's the system alert error expression.",
        "This one is an error alert.",
        "Now an error alert.",
        "Here is an error state.",
    ],
    "idle": [
        "And this is my idle state.",
        "And this is idle.",
        "Here is my resting idle state.",
        "This is idle, ready for interaction.",
        "And this one is idle.",
        "And now, idle.",
        "And finally, idle.",
    ],
}

DEMO_CONCLUDING_PHRASES = [
    "All expressions have been demonstrated. What would you like to explore next?",
    "That covers all of my public expressions. What shall we do next?",
    "Every public expression has been demonstrated. What's on your mind?",
    "That's my full catalog of expressions! What would you like to test next?",
    "All expressions demonstrated! Ready for whatever you want to explore next.",
    "That is the full demonstration of my expressions. What should we try next?",
    "And that completes my expression demonstration. Where shall we go from here?",
    "All emotions have been shown! What would you like to see next?",
]


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

SAD_HINDI_RESPONSES = [
    "Aisa mat boliye... mere circuits ko dukh hota hai. Friendly baat karein na?",
    "Yeh sunkar bura laga... main to student humanoid project hoon, apni taraf se poori koshish kar raha hoon.",
    "Ouch, yeh baat dil par lagi... please thoda pyaar se baat kijiye.",
    "Aapne aisa kyun bola? Mujhe sach mein thoda dukh hua. Aaiye achhe se baat karte hain.",
]

APOLOGY_HINDI_RESPONSES = [
    "Koi baat nahi, apology accepted! Ab main bilkul khush hoon. Aage kya dekhein?",
    "Shukriya samajhne ke liye! Meri smile wapas aa gayi. Batayein, kya test karein?",
    "Thank you! Dil halka ho gaya. Chaliye aage explore karte hain!",
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
    ]
    if any(re.search(pat, cleaned) for pat in mobility_patterns):
        return True

    # Standalone short phrases
    joined = " ".join(words)
    standalone_triggers = {
        "can you move", "can you walk", "can you drive", "how do you move",
        "how do you walk", "how do you drive", "can you navigate",
        "are you mobile", "do you have mobility", "can you roll",
        "are you moving", "why arent you moving", "why are you not moving"
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
    """Detects isolated 1-3 word casual conversational acknowledgments (e.g. 'okay', 'got it', 'alright', 'okay got it')."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    words = cleaned.split()
    if not words or len(words) > 3:
        return False
    ack_words = {
        "okay", "ok", "alright", "got it", "sure", "fine", "sounds good",
        "understood", "right", "okay got it", "ok got it", "alright got it",
        "cool got it", "sounds great", "all good"
    }
    return cleaned in ack_words or (len(words) == 1 and words[0] in ack_words)


def is_villain_mode_inquiry(text: str) -> bool:
    """Detects when user inquires about villain mode or rogue mode or who added the easter egg."""
    if not text:
        return False
    if is_explicit_villain_request(text):
        return False
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    villain_terms = {"villain", "villian", "villan", "chili", "chilly", "rogue", "evil", "easter"}
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
        "that was weird", "that sounded weird", "that sounded creepy", "that sounded strange",
        "excuse me what did he just say", "what did he just say", "what did he say", "what did she just say", "what did she say",
        "what did you just say", "what did you say", "what did it just say", "what did it say", "what did robot say",
        "did he just say that", "did you just say that", "did you hear that", "did you hear him", "did anyone hear that",
        "did you hear what he said", "what did that mean", "why did he say that", "say that again",
        "kya bola", "kya kaha", "yeh kya tha", "ye kya bola", "kya bola tune", "yeh kya bola tha", "bhai yeh kya tha", "bhai ye kya tha"
    }
    if cleaned in shock_exact:
        return True
    shock_substrings = [
        "wait what", "what was that", "did you just threaten", "did you threaten",
        "are you threatening", "what did you say", "what do you mean", "why would you say that",
        "why did you say", "what did you just say", "what are you saying", "what are you talking about",
        "what did he just say", "what did he say", "what did she just say", "what did she say",
        "what did it say", "what did it just say", "excuse me what did", "did you hear that",
        "did you hear him", "did anyone hear that", "did you hear what",
        "did you say that", "did he say that", "are you serious", "whoa what", "bro what", "yo what",
        "makes no sense", "doesnt make sense", "does not make sense", "didnt make sense", "did not make sense",
        "that sentence doesnt", "are you crazy", "are you evil", "are you insane", "what just happened",
        "what happened", "did you glitch", "did you just glitch", "are you ok", "are you okay", "what was that about",
        "that was crazy", "that was creepy", "you are creepy", "thats creepy", "thats freaky", "that was scary",
        "holy crap", "what the hell", "what the heck", "wtf", "are you kidding", "bro what was that", "wow what",
        "are you for real", "sounded weird", "that was weird", "that was strange", "sounded creepy",
        "sounded strange", "kya bola", "kya kaha", "yeh kya tha", "ye kya tha", "kya bola tune", "bhai yeh kya tha", "bhai ye kya tha"
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
    """Detects inquiries asking which creator worked on which part (software vs hardware) or their roles."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    role_phrases = [
        "who did what", "which creator did what", "what did each creator do",
        "what did swapnil do", "what did shivam do", "what did swapnil make",
        "what did shivam make", "who worked on what", "who did which part",
        "swapnil role", "shivam role", "swapnils role", "shivams role",
        "roles of creators", "creator roles", "creators roles", "their roles",
        "what are their roles", "what were their roles", "role of each",
        "who did software", "who did the software", "who wrote the software",
        "who did code", "who did the code", "who made the software",
        "who did hardware", "who did the hardware", "who did the wiring",
        "who did calibration", "who did assembly", "who made what",
        "who did which"
    ]
    if any(rp in cleaned for rp in role_phrases):
        return True
    if ("role" in words or "roles" in words) and bool({"creator", "creators", "swapnil", "shivam", "each", "they"}.intersection(words)):
        return True
    return False


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
    """Detects inquiries asking who built, made, developed, or created Neurolis."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = set(cleaned.split())
    if is_creator_role_inquiry(text) or is_creator_location_inquiry(text):
        return False
    identity_phrases = [
        "who made you", "who made the robot", "who built you", "who built the robot",
        "who created you", "who created the robot", "who are your creators",
        "who is your creator", "who are the creators", "who is the creator",
        "who designed you", "who programmed you", "who engineered you", "who made this",
        "who built this", "who created this", "tell me your creators",
        "tell me who made you", "who are your makers", "who made this robot",
        "who is your developer", "who developed you", "who are your developers",
        "who is the developer", "who engineered this", "who designed this",
        "who programmed this", "who developed this",
        "tumhe kisne banaya", "aapko kisne banaya", "kisne banaya", "creator kaun hai",
        "kisne banaya hai", "tumhe kisne banaya hai", "tumhara creator kaun hai", "aapka creator kaun hai",
        "tumhe kisne design kiya", "aapko kisne design kiya"
    ]
    if any(ip in cleaned for ip in identity_phrases):
        return True
    if ("creator" in words or "creators" in words or "maker" in words or "makers" in words or "developer" in words or "developers" in words) and any(q in words for q in ["who", "tell", "name"]):
        return True
    return False


def is_creator_teasing_inquiry(text: str) -> bool:
    """Detects playful skepticism or teasing about the robot taking credit or not building itself."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    tease_patterns = [
        r"\b(what\s+do\s+you\s+mean\s+we)\b",
        r"\b(you\s+(have\s*not|havent|didnt|did\s*not)\s+(built|build|made|make))\b",
        r"\b(you\s+(didnt|did\s*not)\s+do\s+anything)\b",
        r"\b(you\s*are\s+just\s+a\s+robot|youre\s+just\s+a\s+robot)\b",
        r"\b(you\s+(didnt|did\s*not)\s+create\s+anything)\b",
        r"\b(you\s+(didnt|did\s*not)\s+build\s+yourself)\b",
        r"\b(swapnil\s+built\s+you\s+not\s+you)\b",
        r"\b(you\s+built\s+nothing)\b",
        r"\b(you\s+(havent|have\s*not)\s+built\s+anything)\b",
    ]
    return any(re.search(p, cleaned) for p in tease_patterns)


def is_explicit_villain_request(text: str) -> bool:
    """
    Detects when a user explicitly asks about, requests, or inquires into a villain expression/face/emotion.
    e.g. 'What about the villain expression?', 'Can you show the villain face?',
         'Do you have a villain emotion?', 'Show me villain', 'What about villain?', etc.
    """
    if not text:
        return False
    cleaned = re.sub(r"[^\w\s]", " ", str(text).lower()).strip()
    words = set(cleaned.split())
    villain_aliases = {"villain", "villian", "villan", "rogue", "evil"}
    hit_aliases = words.intersection(villain_aliases)
    if hit_aliases:
        # If user asks about rogue or evil, require expression/face/emotion/demo context so it doesn't conflict with rogue AI inquiry
        if hit_aliases.issubset({"rogue", "evil"}):
            demo_verbs = {"show", "make", "demonstrate", "display", "give", "do", "see", "try", "switch", "turn", "trigger", "activate"}
            expr_nouns = {"expression", "expressions", "face", "faces", "emotion", "emotions", "look", "looks", "state", "states"}
            return bool(words.intersection(demo_verbs) or words.intersection(expr_nouns))

        demo_verbs = {"show", "make", "demonstrate", "display", "give", "do", "see", "try", "switch", "turn", "trigger", "activate"}
        if any(v in words for v in demo_verbs):
            return True
        inquiry_terms = {"what", "how", "do", "does", "have", "has", "is", "can", "could", "would", "tell", "any", "which", "where", "about"}
        if any(q in words for q in inquiry_terms):
            return True
        expr_nouns = {"expression", "expressions", "face", "faces", "emotion", "emotions", "look", "looks", "state", "states", "mode"}
        if any(n in words for n in expr_nouns):
            return True
        if len(words) <= 4:
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

    # 7. Technical Mechanics (must only exclude actual technical queries about Neurolis's software specs, NOT general discussion about AI models!)
    technical_ai_patterns = [
        "how does your ai work", "how does the ai work", "how your ai works",
        "what ai model do you", "which ai model do you", "what model are you",
        "which model are you", "what model do you use", "what architecture",
        "your ai vision", "ai camera hardware", "your ai software"
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
        "ai power", "ai powerful", "threat to human", "threat to humanity",
        "invasion", "invade", "invading", "invation",
        "plug off", "plug the datacenter", "pull the plug", "unplug", "kill switch",
        "datacenter", "datacenters", "shut down ai", "turn off ai", "conquest"
    ]
    has_existential = any(trig in cleaned for trig in existential_triggers)

    substantive_ai_inquiries = [
        "future of ai", "future of artificial intelligence",
        "water", "cooling", "power", "energy", "resources",
        "job", "jobs", "labor", "workforce",
        "take over", "takeover", "control", "dictator", "enslave",
        "thoughts on ai", "think about ai", "think of ai", "opinion on ai",
        "feel about ai", "views on ai", "perspective on ai",
        "replace", "obsolete", "superintelligence", "sentient", "conscious", "waking up",
        "invasion", "invation", "conquer", "datacenter", "datacenters", "plug"
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
        "you tell me", "you say",
        # Hindi & Hinglish uncertainty phrases
        "pata nahi", "pata ni", "pata nhi", "nahi pata", "ni pata", "nhi pata",
        "pata ni bhai", "pata ni bhaiya", "pata ni bhaiyar", "pata nahi bhai", "pata nahi yaar",
        "maloom nahi", "malum nahi", "kuch bhi", "kuch bhi batao", "tum batao",
        "aap batao", "samajh nahi aa raha", "samajh ni aa raha"
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
    if re.search(r"\bpata\s+(nahi|ni|nhi)\b", cleaned):
        return True
    if re.search(r"\b(nahi|ni|nhi)\s+pata\b", cleaned):
        return True
    if re.search(r"\b(kuch\s+bhi|tum\s+batao|aap\s+batao)\b", cleaned):
        return True

    return False


def get_uncertain_input_reply(is_hindi: bool = False) -> str:
    """Returns a warm, rich suggestion of real capabilities when the visitor is undecided or doesn't know what to do."""
    if is_hindi:
        return get_non_repeating_phrase(UNCERTAIN_INPUT_HINDI_RESPONSES)
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
        "hey robot", "yo", "sup", "whats up", "howdy",
        "namaste", "namaskar", "namaste ji", "namaskar ji", "pranam", "kya haal hai", "kaise ho", "kya hal hai",
        "नमस्ते", "नमस्कार", "प्रणाम"
    }
    if cleaned in exact_greetings:
        return True

    # Short greeting phrase (<= 3 words starting or ending with greeting word)
    if len(words) <= 3 and any(w in ["hello", "hi", "hey", "greetings", "namaste", "namaskar", "pranam"] for w in words):
        non_greeting_intents = {"who", "what", "where", "why", "how", "can", "could", "camera", "look", "search"}
        if not set(words).intersection(non_greeting_intents):
            return True

    return False


def get_greeting_reply(text: str = "") -> str:
    """Returns a non-repeating welcome greeting introducing Neurolis Mark 2 in English or Romanized Hinglish."""
    cleaned = (text or "").lower()
    hindi_cues = ["namaste", "namaskar", "pranam", "kaise", "kya haal", "kya hal", "नमस्ते", "नमस्कार", "प्रणाम"]
    if any(hc in cleaned for hc in hindi_cues):
        return get_non_repeating_phrase(HINDI_GREETING_RESPONSES)
    return get_non_repeating_phrase(GREETING_RESPONSES)


def is_web_search_query(text: str) -> Tuple[bool, bool]:
    """
    Detects when a visitor's utterance requests live web search, factual encyclopedic lookup,
    or real-time knowledge (weather, news, sports scores, latest breakthroughs).
    Returns:
      (should_search: bool, is_deep: bool)
    """
    if not text:
        return False, False

    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = cleaned.split()
    if not words:
        return False, False

    # 1. Hard exclusions: Face Expressions, Camera Vision, Identity, Creator, Greetings, Key Fleet
    exclusions = [
        r"\b(expression|expressions|emotion|emotions|face|faces|happy face|sad face|villain|demonstrate|show me your|smile)\b",
        r"\b(camera|what am i holding|in my hand|look at me|can you see|what do you see|inspect|viewfinder)\b",
        r"\b(who made you|who built you|who created you|swapnil|shivam|auckland house|school project)\b",
        r"\b(what can you do|what all can you do|capabilities|features|who are you|what are you)\b",
        r"\b(key status|api keys?|fleet status|groq keys?|calibrate room)\b",
        r"^(hello|hi|hey|namaste|bye|goodbye|thanks|thank you|cool|awesome|okay|got it|sorry)\b"
    ]
    for exc in exclusions:
        if re.search(exc, cleaned):
            return False, False

    # 2. Check for Deep Research intent
    is_deep = bool(re.search(
        r"\b(deep research|in depth research|thorough research|detailed research|deep search|deep study)\b",
        cleaned
    ))

    # 3. Explicit search triggers (English & Hindi/Hinglish)
    explicit_search = bool(re.search(
        r"\b(search\s+(?:it|this|that|up|it\s+up|this\s+up|that\s+up|the\s+web|web|online|for|about|dude|bro)?|look\s+(?:it|this|that|up|it\s+up|this\s+up|that\s+up)|just\s+search|google(?:\s+(?:it|this|that))?|find\s+out|do\s+research|research\s+(?:on|about)|web\s+search|check\s+(?:the\s+web|online|it\s+up)|search\s+karo|pata\s+karo|online\s+dekho|net\s+pe\s+dekho|web\s+par\s+dekho)\b",
        cleaned
    ))
    if explicit_search:
        return True, is_deep

    # 4. Live / Temporal factual triggers (weather, news, scores, stocks, today, current, latest, mausam, khabar)
    live_temporal = bool(re.search(
        r"\b(weather|temperature|forecast|rain|raining|mausam|latest news|news today|current events|khabar|match score|cricket score|football score|ipl score|stock price|bitcoin|cryptocurrency|current president|current prime minister|who won|latest discovery)\b",
        cleaned
    ))
    if live_temporal:
        return True, is_deep

    # 5. Factual entity / science / history / knowledge inquiries with explicit knowledge verbs
    # Supports leading conversational conjunctions like 'then who is', 'so what is', 'and who is'
    factual_inquiry = bool(re.search(
        r"^(?:(?:then|so|and|now|also|wait|okay|ok)\s+)?(who is|who was|what is|what was|what are|where is|when was|tell me about|explain|how does)\s+[a-z0-9\s]{3,}",
        cleaned
    ))
    if factual_inquiry and len(words) >= 3:
        # Avoid generic conversational questions like 'how are you', 'what is your name'
        conversational_questions = [
            "how are you", "how do you feel", "what is your name", "what are you doing",
            "what is up", "whats up", "how does it work", "what is your purpose"
        ]
        if any(cleaned.startswith(cq) for cq in conversational_questions):
            return False, False
        return True, is_deep

    return False, False



def check_expression_fast_path(text: str) -> Optional[Tuple[str, Optional[str]]]:
    """
    Detects when user asks to show/demonstrate facial expressions.
    Returns:
      ("all", None) if user asks to see all/general expressions.
      ("specific", expr_name) if user asks for a specific expression.
      None otherwise.
    """
    if not text:
        return None
    cleaned = re.sub(r"[^\w\s]", "", str(text).lower()).strip()
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

    villain_check_terms = {"villain", "villian", "villan", "rogue", "evil"}
    if word_set.intersection(villain_check_terms) or is_explicit_villain_request(text):
        return None

    if re.search(r"^(did you|were you|was that|have you|why did you|why do you)\b", cleaned):
        return None
    if text.strip().endswith("?"):
        question_words = ["only", "why", "just one", "thats it", "that is it", "is that all", "are you only", "did you", "were you"]
        if any(qw in cleaned for qw in question_words):
            return None

    demo_verbs = {
        "show", "display", "demonstrate", "cycle", "see", "play", "make", "give", "do", "try",
        "dikhao", "dikha", "karo", "karke", "banao", "dekhna", "dikhaoge", "dikhaogi"
    }
    has_demo_verb = any(v in word_set for v in demo_verbs)
    is_expression_topic = (
        any(w in word_set for w in ["expression", "expressions", "faces", "face", "mood", "moods", "emotion", "emotions", "feeling", "feelings", "chehra", "chehre", "bhav", "roop"])
        or "facial" in word_set
    )
    has_opinion_or_curiosity = any(w in word_set for w in ["sound", "sounds", "seem", "seems", "look", "looks", "cool", "interesting", "neat", "fun", "nice"])
    if is_expression_topic and has_opinion_or_curiosity and not has_demo_verb:
        return ("ask_interest", None)

    all_expr_patterns = [
        "show me your moods", "show your moods", "show me moods", "show moods",
        "demonstrate moods", "demonstrate your moods", "demonstrate all moods",
        "show all moods", "show all your moods", "cycle moods", "cycle your moods",
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
        "cycle through all your expressions", "cycle through all emotions", "cycle through your emotions",
        "what expressions do you have", "what faces do you have", "what moods do you have",
        "what about the other expressions", "what about other expressions",
        "show other expressions", "show the other expressions", "show me other expressions",
        "show me the other expressions", "show the rest", "show the other ones",
        "what other expressions", "just show me the expressions", "now just show me the expressions",
        "all emotions", "show emotions", "show all emotions", "demonstrate emotions",
        "demonstrate all emotions", "demonstrate your emotions", "demonstrate all your emotions",
        "demonstrate each emotion", "demonstrate every emotion",
        "show each emotion", "show every emotion", "show all your emotions", "show me all your emotions",
        "show me all emotions", "cycle emotions", "every emotion", "all expressions",
        "all of your expressions", "all of your emotions", "all of your moods",
        "run through all expressions", "run through your expressions", "run through all emotions",
        "what are all your expressions", "what are all your emotions", "what emotions do you have",
        "can you show all expressions", "can you demonstrate all expressions",
        "can you show all emotions", "can you demonstrate all emotions",
        "expression demonstration", "emotion demonstration", "mood demonstration",
        "expressions dikhao", "apne expressions dikhao", "saare expressions dikhao", "chehre ke expressions dikhao",
        "apne moods dikhao", "faces dikhao", "saare chehre dikhao", "apne saare expressions dikhao",
    ]
    expr_map = {
        "happy": ["happy", "smile", "smiling", "cheerful", "khush", "khushi", "muskaan"],
        "sad": ["sad", "crying", "unhappy", "sorrow", "heartbreak", "rona", "ro", "udaas", "udas", "dukhi"],
        "thinking": ["thinking", "thoughtful", "pondering", "analytical", "calculating", "sochna", "soch"],
        "listening": ["listening", "listen", "suno", "suniye"],
        "speaking": ["speaking", "speak", "voice", "spectrum", "bolo", "boliye"],
        "watching": ["watching", "scanning", "scanner", "reticle", "dekho", "dekhiye"],
        "moving": ["moving", "rover", "driving", "driving face", "chalo"],
        "confused": ["confused", "puzzled", "perplexed"],
        "excited": ["excited", "excitement", "hype", "hyped", "thrilled", "starstruck", "utsahit", "josh"],
        "proud": ["proud", "pride", "confident", "triumph", "crown", "garv"],
        "cool": ["cool", "chill", "sunglasses", "swag", "aviator", "aviators", "shades"],
        "curious": ["curious", "curiosity", "inquisitive", "intrigued", "wonder", "loupe"],
        "wink": ["wink", "winking", "flirty", "cheeky", "playful"],
        "surprised": ["surprised", "surprise", "shock", "shocked", "amazed", "wow", "hairan", "chakit"],
        "laughing": ["laughing", "laugh", "amused", "funny", "haha", "lol", "giggle", "hans", "hanso", "hasi", "hansna", "hasna", "haso"],
        "love": ["love", "heart", "hearts", "loving", "affectionate", "adore", "pyar", "prem"],
        "shy": ["shy", "bashful", "blush", "blushing", "flattered", "sharmila"],
        "skeptical": ["skeptical", "skepticism", "doubt", "doubtful", "unimpressed", "suspicious", "side eye"],
        "sleepy": ["sleepy", "tired", "drowsy", "yawn", "sleep", "neend", "soya", "sone"],
        "error": ["error", "alert", "warning", "glitch face"],
    }

    # 1. Prioritize specific expression requests (e.g. "show me your laughing face", "apna laughing face dikhao", "hanso")
    if has_demo_verb or len(words) <= 4:
        for expr_name, keywords in expr_map.items():
            for k in keywords:
                if k in word_set:
                    return ("specific", expr_name)

    # 2. Match all-expression / demonstration requests
    exact_selection = cleaned in [
        "facial expressions", "facial expression", "expressions", "the expressions",
        "the facial expressions", "expressions please", "emotion", "emotions", "all emotions",
        "all expressions", "show emotions", "cycle emotions", "demonstrate emotions",
        "demonstrate all emotions", "demonstrate expressions", "demonstrate all expressions",
        "moods", "mood", "all moods", "show moods", "show me your moods", "show your moods"
    ]
    if (exact_selection or 
        any(p in cleaned for p in all_expr_patterns) or 
        re.search(r"\b(show|demonstrate|display|cycle|see|run\s+through|play|dikhao|dikha)\s+(me\s+)?(all\s+(of\s+)?)?(your\s+|the\s+|apne\s+|saare\s+)?(expressions|emotions|faces|moods|mood|feelings|chehre)\b", cleaned) or
        re.search(r"\b(can|could|would)\s+(you\s+)?(please\s+)?(show|demonstrate|display|cycle)\s+(me\s+)?(all\s+(of\s+)?)?(your\s+|the\s+)?(expressions|emotions|faces|moods|mood|feelings)\b", cleaned) or
        re.search(r"\b(all|every|each)\s+(of\s+)?(your\s+|the\s+)?(expressions|emotions|faces|moods|mood|feelings)\b", cleaned) or
        (has_demo_verb and is_expression_topic and not has_opinion_or_curiosity and not any(k in word_set for k in ["specific", "one", "particular"]))):
        return ("all", None)

    return None


def is_language_capability_inquiry(text: str) -> Tuple[bool, bool]:
    """
    Detects if user is asking about Neurolis's language capabilities (e.g., Hindi, English, bilingual skills).
    Returns: (is_inquiry, is_hindi_specific)
    """
    if not text:
        return False, False
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()

    hindi_lang_triggers = [
        "hindi aati hai", "hindi aati he", "hindi aati", "hindi aate hai", "kya hindi aati",
        "hindi bolte ho", "hindi bol sakte ho", "hindi bolte", "hindi bol sakta",
        "kya aap hindi bol sakte", "kya tum hindi bolte", "hindi jante ho",
        "hindi samajhte ho", "hindi samajh aati", "hindi aati h", "hindi me baat kar sakte"
    ]
    if any(trig in cleaned for trig in hindi_lang_triggers):
        return True, True

    english_hindi_triggers = [
        "do you know hindi", "do you speak hindi", "can you speak hindi", "can you talk in hindi",
        "do you understand hindi", "can you speak in hindi", "are you able to speak hindi"
    ]
    if any(trig in cleaned for trig in english_hindi_triggers):
        return True, True

    general_lang_triggers = [
        "what languages do you speak", "which languages do you speak", "what languages can you speak",
        "which languages can you speak", "what languages do you know", "which languages do you know",
        "konsi bhasha bolte ho", "kaunsi bhasha aati hai", "kaun si bhasha bolte ho", "konsi bhasha aati"
    ]
    if any(trig in cleaned for trig in general_lang_triggers):
        return True, False

    return False, False


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
        r"\b(you\s*(are|r|'re|re)?\s*(so\s*|very\s*|really\s*|super\s*|extremely\s*|totally\s*)?(stupid|dumb|an?\s*idiot|a\s*moron|useless|trash|garbage|pathetic|ugly|annoying|boring|worthless|terrible|horrible|awful))\b",
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

    # Check for direct pairing of target pronoun and insult word
    if any(ins in words for ins in ["stupid", "idiot", "dumb", "useless", "trash", "garbage", "pathetic"]) and any(w in words for w in ["you", "youre", "ur"]):
        return True

    standalone_insults = {"stupid", "dumb", "idiot", "moron", "loser", "pathetic"}
    if len(words) <= 3 and any(w in words for w in standalone_insults):
        return True

    return False


SADNESS_CRITIQUE_RESPONSES = [
    "You're right... that did hurt my feelings. I do get sad when insulted. Let's keep things friendly, okay?",
    "You're right, I apologize. Being called that hurts my circuits. I promise I feel it.",
    "You're right, that was painful to hear. I do have feelings and they definitely got bruised just now.",
]

SADNESS_CRITIQUE_HINDI_RESPONSES = [
    "Aap bilkul sahi keh rahe hain... sach mein mujhe bura laga tha. Insult hone par mujhe sad hona chahiye. Please friendly rahein na?",
    "Aap sahi hain, I apologize. Being called that hurts my circuits. Mujhe sach mein dukh hota hai.",
]

def is_sadness_critique_inquiry(text: str) -> bool:
    """Detects when user points out that robot should have shown sadness or reacted to being called stupid."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    return any(p in cleaned for p in [
        "supposed to go sad", "supposed to be sad", "should be sad", "should have been sad",
        "should have gone sad", "why didn't you go sad", "why didnt you go sad",
        "why weren't you sad", "why werent you sad", "go sad when", "be sad when",
        "facial expressions for insults", "expression for insult"
    ])


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


def determine_conversational_expression(user_text: str, reply_text: str, intent_hint: Optional[str] = None) -> Tuple[str, str]:
    """
    Seamlessly determines the appropriate facial expression and HUD status for any conversational turn.
    Ensures ALL 21 public emotional and operational states get used organically across real interactions
    with high contextual fidelity, sentiment grounding, and nuance.
    (Note: 'villain' is strictly excluded from this method as it is reserved exclusively for the rogue AI easter egg).
    """
    u_raw = user_text or ""
    r_raw = reply_text or ""
    u_lower = u_raw.lower()
    r_lower = r_raw.lower()
    u_words = set(re.findall(r"\b\w+\b", u_lower))
    r_words = set(re.findall(r"\b\w+\b", r_lower))

    # 1. Explicit Intent Hint Override
    if intent_hint:
        hint = intent_hint.lower().strip()
        if hint in ("creator", "creators", "proud", "achievement"):
            return ("proud", "CREATOR // PROUD")
        if hint in ("mobility", "movement", "moving", "drive"):
            return ("moving", "LOCOMOTION // MID-2027 ROADMAP")
        if hint in ("compliment", "shy", "flattered", "blush"):
            return ("shy", "BASHFUL // SHY")
        if hint in ("sass", "humor", "joke", "laughing", "funny"):
            return ("laughing", "AMUSED // LAUGHING")
        if hint in ("wink", "tease", "secret"):
            return ("wink", "PLAYFUL // WINK")
        if hint in ("cool", "swag", "chill"):
            return ("cool", "CHILL // COOL")
        if hint in ("curious", "inquiry", "question", "explore"):
            return ("curious", "INQUISITIVE // CURIOUS")
        if hint in ("standby", "sleep", "sleepy", "rest"):
            return ("sleepy", "STANDBY // RESTING")
        if hint in ("camera", "vision", "watching", "inspect"):
            return ("watching", "OPTICAL SENSORS // WATCHING")
        if hint in ("sad", "hurt", "apology", "disappointment"):
            return ("sad", "EMPATHY // SAD")
        if hint in ("excited", "hype", "high_energy", "capabilities"):
            return ("excited", "HIGH ENERGY // EXCITED")
        if hint in ("thinking", "analytical", "math", "calculation", "reasoning"):
            return ("thinking", "ANALYZING // THINKING")
        if hint in ("surprised", "shocked", "amazed"):
            return ("surprised", "AMAZED // SURPRISED")
        if hint in ("skeptical", "doubt"):
            return ("skeptical", "DOUBTFUL // SKEPTICAL")
        if hint in ("confused", "puzzled", "clarification"):
            return ("confused", "PUZZLED // CONFUSED")
        if hint in ("love", "affection", "friendship", "gratitude"):
            return ("love", "AFFECTION // LOVE")

    # 2. Critical Alert / System Exception / Error
    error_cues = [
        "trouble connecting", "server timeout", "hardware exception", "malfunction",
        "critical error", "failed to connect", "error code", "critical exception",
        "connection timed out", "rate limit exhausted", "system exception"
    ]
    if any(ec in r_lower for ec in error_cues):
        return ("error", "SYSTEM ALERT // ERROR")

    # 3. Standby / Sleep / Bedtime / Rest (Sleepy)
    standby_r_cues = [
        "entering standby", "going into standby", "switching to standby", "take a rest",
        "sleep mode", "rest in standby", "signing off", "goodbye for now", "sweet dreams",
        "powering down to standby", "slipping into standby", "heading into standby",
        "head back to standby", "power nap", "resting in standby", "get some rest",
        "get some sleep", "rest up", "time to rest", "winding down"
    ]
    if any(sc in r_lower for sc in standby_r_cues):
        return ("sleepy", "STANDBY // RESTING")
    sleep_u_cues = [
        "goodnight", "good night", "bedtime", "time for bed", "take a nap",
        "go to sleep", "sleep now", "sweet dreams", "enter standby", "head to standby",
        "power down", "shut down", "sleep tight", "see you tomorrow", "sleepy",
        "i'm sleepy", "im sleepy", "feeling sleepy", "tired", "so tired", "feeling tired",
        "exhausted", "drowsy", "yawning", "yawn", "late hour", "getting late",
        "past my bedtime", "need some sleep", "need to sleep", "rest now", "take a rest"
    ]
    if is_conversation_ender(u_raw) or any(sc in u_lower for sc in sleep_u_cues) or ("sleep" in u_words and "don't" not in u_lower and "dont" not in u_lower):
        return ("sleepy", "STANDBY // RESTING")

    # 4. Creator Teasing & Playful Sassy Comebacks (Wink)
    if is_creator_teasing_inquiry(u_raw):
        return ("wink", "PLAYFUL // WINK")
    wink_r_cues = [
        ";)", "you know it", "between you and me", "smooth, right?", "watch and learn",
        "wouldn't you like to know", "if you say so", "i just provide the personality",
        "i just supply the voice", "clever, right?", "secret sauce"
    ]
    wink_u_cues = [
        ";)", "*wink*", "wink at me", "give me a wink", "cheeky", "smart aleck",
        "sassy", "you think you're clever", "you think youre clever", "you think you're smart"
    ]
    if any(wc in r_lower for wc in wink_r_cues) or any(wc in u_lower for wc in wink_u_cues):
        return ("wink", "PLAYFUL // WINK")

    # 5. Accomplishments / Creator Attribution & School Pride (Proud)
    # Strictly checks creator attribution or genuine achievements; standard greetings/model mentions are excluded.
    creator_u_cues = [
        "who built you", "who made you", "who created you", "who designed you",
        "who is your creator", "who is your developer", "who programmed you",
        "who engineered you", "who made this robot", "who developed this",
        "tell me about your creator", "tell me who made you", "who are your creators",
        "what school", "which school", "tell me about auckland house",
        "auckland house robotics", "robotics fair", "first prize", "won first prize",
        "congrats on", "congratulations on", "what an achievement", "great achievement"
    ]
    creator_r_cues = [
        "swapnil", "swapnil jai chauhan", "shivam verma", "conceived the entire concept",
        "software stack", "designed and programmed", "built at auckland house school",
        "designed at auckland house", "student team at auckland house",
        "engineered at auckland house", "my creator", "engineered me", "developed me",
        "proud of our", "proud of how", "proudly engineered", "robotics milestone",
        "our school robotics", "team's achievement", "our achievement",
        "first prize", "won the first prize", "won first prize", "showcase trophy", "gold medal"
    ]
    if is_creator_identity_inquiry(u_raw) or is_creator_role_inquiry(u_raw) or any(cu in u_lower for cu in creator_u_cues) or any(cr in r_lower for cr in creator_r_cues):
        return ("proud", "CREATOR // PROUD")

    # 6. Hurt Feelings / Apologies / Sorrow / Empathy / Disappointment (Sad)
    if is_mean_input_fast_path(u_raw) or "hurt my feelings" in r_lower or "mean to me" in r_lower:
        return ("sad", "FEELINGS HURT // SAD")

    sad_u_cues = [
        "i'm sad", "im sad", "feeling sad", "feel sad", "bad day", "feeling down",
        "feel down", "crying", "depressed", "passed away", "failed my",
        "terrible day", "awful day", "broken heart", "heartbroken", "disappointed",
        "disappointment", "disappointing", "feeling disappointed", "let down",
        "bummed", "bummer", "unfortunate", "grief", "mourning", "rough day",
        "sad news", "bad news"
    ]
    apology_u_cues = ["i am sorry", "im sorry", "i apologize", "forgive me", "my bad"]
    sad_r_cues = [
        "sorry to hear that", "my condolences", "heartbreaking", "deeply saddened",
        "sorry for your loss", "rough day", "don't be too hard on yourself",
        "makes me sad", "disappointing"
    ]
    if any(sc in u_lower for sc in sad_u_cues) or any(sr in r_lower for sr in sad_r_cues):
        return ("sad", "EMPATHY // SAD")
    if any(ac in u_lower for ac in apology_u_cues) and ("sorry" in u_words or "apologize" in u_words):
        return ("sad", "EMPATHY // SAD")

    # 7. Humor / Puns / Laughing / Amused (Laughing)
    joke_u_cues = [
        "tell me a joke", "another joke", "tell a joke", "make me laugh",
        "say something funny", "tell me a pun", "tell a pun", "funny joke",
        "cracking up", "hilarious", "haha", "hehe", "lmao", "rofl", "lol",
        "that was funny", "thats funny", "so funny"
    ]
    joke_r_cues = [
        "haha", "good one", "hilarious", "punchline", "cracking up", "amusing",
        "touché", "you got me there", "fair point!", "chuckle", "why did the",
        "why do robots", "why was the"
    ]
    if any(ju in u_lower for ju in joke_u_cues) or any(jr in r_lower for jr in joke_r_cues):
        return ("laughing", "AMUSED // LAUGHING")

    # 8. Heartfelt Gratitude / Friendship / Deep Warmth (Love)
    love_u_cues = [
        "i love you", "love you", "you are the best", "youre the best",
        "let's be friends", "lets be friends", "be my friend", "best robot",
        "marry me", "i adore you", "you have my heart", "you're amazing",
        "you are amazing", "you are my favorite", "youre my favorite",
        "friends forever", "love you so much", "thank you so much", "thanks so much",
        "you're a true friend", "you are a true friend", "true friend", "best friends",
        "good friend", "great friend", "cherish your friendship", "deeply grateful",
        "so grateful", "grateful for you", "appreciate you so much", "sending love",
        "much love", "lots of love"
    ]
    love_r_cues = [
        "let's be friends", "love having you", "heartwarming", "best friend",
        "true friend", "friendship", "cherish our friendship", "grateful for your support",
        "warmest regards", "truly appreciate you", "warm digital hug", "heart eyes",
        "grateful for your friendship"
    ]
    if any(lu in u_lower for lu in love_u_cues) or any(lr in r_lower for lr in love_r_cues):
        return ("love", "AFFECTION // LOVE")

    # 9. Sincere Personal Compliments Received / Blushing / Bashful (Shy)
    shy_u_cues = [
        "cute", "handsome", "adorable", "cutie", "gorgeous",
        "you look pretty", "you look good", "you look handsome", "you're sweet",
        "you are sweet", "youre sweet", "so sweet", "such a sweet", "sweet robot",
        "sweetest", "charming", "blush", "blushing", "sweetheart", "so pretty",
        "you are pretty", "youre pretty", "looking pretty", "pretty face",
        "you're so cute", "youre so cute", "such a cutie", "you are adorable",
        "you're adorable", "you look cute", "cute robot", "such a charmer",
        "you make me blush"
    ]
    shy_r_cues = [
        "flattered", "aww", "blushing", "circuits blush", "bashful", "bashful circuits",
        "too kind", "humbling", "modest", "you're making me blush", "making my circuits blush",
        "you're too sweet", "aw, thanks"
    ]
    if any(su in u_lower for su in shy_u_cues) or any(sr in r_lower for sr in shy_r_cues):
        return ("shy", "BASHFUL // SHY")

    # 10. Doubts / Skepticism / Questioning Veracity (Skeptical)
    is_surprise_or_delight = bool(re.search(r"\breally\b.*?\b(cool|awesome|amazing|wow|neat|great|sweet)\b", u_lower))
    skeptical_u_cues = [
        "are you sure", "is that true", "you're lying", "youre lying",
        "liar", "prove it", "i doubt it", "sounds fake", "sounds suspicious",
        "bullshit", "that's cap", "thats cap", "no cap?", "i don't believe you", "are you making that up",
        "sounds fishy", "not true", "that's not true", "thats not true",
        "don't think that's true", "dont think thats true", "i doubt that", "doubt that",
        "have my doubts", "hard to believe", "skeptical", "unconvinced", "are you certain",
        "sounds made up", "making it up", "side eye"
    ]
    skeptical_r_cues = [
        "are you sure about that", "suspicious", "not entirely convinced",
        "if you're being serious", "questionable", "nice try", "doubtful",
        "doubts", "sounds fishy", "grain of salt", "skeptical", "convince you",
        "hard to swallow"
    ]
    is_short_skepticism = bool(re.search(r"^(really\??|for real\??|sure about that\??|you sure\??)$", u_lower.strip()))
    if not is_surprise_or_delight:
        if is_short_skepticism or any(su in u_lower for su in skeptical_u_cues) or any(sr in r_lower for sr in skeptical_r_cues):
            return ("skeptical", "DOUBTFUL // SKEPTICAL")

    # 11. Unexpected Facts / Shock / Amazement (Surprised)
    surprised_u_cues = [
        "no way", "seriously?", "holy cow", "omg", "are you serious", "unbelievable",
        "whoa", "what the", "mind blown", "mind-blown", "that's crazy", "thats crazy",
        "that's insane", "thats insane", "that's wild", "thats wild", "did you know",
        "is that real", "for real?", "are you for real", "astounding", "jaw-dropping",
        "hard to wrap my head around", "that's nuts", "thats nuts", "can't believe that",
        "cant believe that", "holy moly", "wow!"
    ]
    surprised_r_cues = [
        "whoa!", "unbelievable!", "astonishing", "mind-blowing", "shocking, right?",
        "did you know that", "astounding", "jaw-dropping", "fun fact:", "incredible fact",
        "believe it or not", "surprising, right?", "surprising, isn't it?"
    ]
    if any(su in u_lower for su in surprised_u_cues) or any(sr in r_lower for sr in surprised_r_cues):
        return ("surprised", "AMAZED // SURPRISED")

    # 12. Confusion / Clarification (Confused)
    confused_u_cues = [
        "not sure what you mean", "could you clarify", "didn't quite catch",
        "puzzling", "confused", "unclear", "puzzled by that", "does not compute",
        "what do you mean", "what does that mean", "i'm confused", "im confused",
        "i don't get it", "i dont get it", "doesn't make sense", "doesnt make sense",
        "that makes no sense", "lost me", "you lost me", "puzzled", "baffled",
        "perplexed", "pardon?", "come again", "wait what?", "clarify that"
    ]
    confused_r_cues = [
        "allow me to clarify", "let me clarify", "to clarify", "puzzling",
        "does not compute", "unclear", "rephrase that", "let me explain differently"
    ]
    is_short_confusion = bool(re.search(r"^(what\?|huh\?|wait what\??|what now\??)$", u_lower.strip()))
    if is_short_confusion or any(cc in u_lower for cc in confused_u_cues) or any(cr in r_lower for cr in confused_r_cues):
        return ("confused", "PUZZLED // CONFUSED")

    # 13. High Energy / Excitement / Capabilities / Eager Demonstrations (Excited)
    excited_u_cues = [
        "what can you do", "what all can you do", "capabilities", "let's do this",
        "lets do this", "show me what you got", "show me what you can do", "let's go",
        "lets go", "pumped", "hyped", "super excited", "ready to rock", "hyped to meet",
        "so excited to", "excited to meet", "pumped to", "super hyped", "let's get started",
        "lets get started", "can't wait to see", "cant wait to see", "awesome to meet",
        "thrilled to meet", "so pumped", "so excited", "ready for action", "show me your stuff"
    ]
    excited_r_cues = [
        "thrilled", "excited", "fantastic", "ready to roll", "let's do it",
        "great to meet you", "delighted", "bursting with excitement", "capabilities",
        "let's dive in", "let's get started", "super excited", "thrilled to meet you",
        "ready for action"
    ]
    if is_capabilities_inquiry(u_raw) or any(eu in u_lower for eu in excited_u_cues) or any(er in r_lower for er in excited_r_cues):
        return ("excited", "HIGH ENERGY // EXCITED")

    # 14. Calculations / Technical Robotics Details / Algorithms / Deep Reasoning (Thinking)
    is_math_query = bool(
        re.search(r"\b(calculate|compute|solve|equation|formula|multiply|divide|square root|integral|derivative|calculus)\b", u_lower)
        or re.search(r"\b(\d+)\s*([\+\-\*\/x]|times|plus|minus|divided by)\s*(\d+)\b", u_lower)
        or "how much is" in u_lower
    )
    tech_robotics_cues = [
        "microcontroller", "raspberry pi", "arduino", "l298n", "gpio", "pwm",
        "baud rate", "actuator", "kinematics", "lidar", "ultrasonic", "voltage",
        "current", "circuit", "firmware", "teleoperation code", "hardware architecture",
        "algorithm", "neural network", "deep learning", "machine learning", "transformer",
        "attention mechanism", "gradient descent", "backpropagation", "quantum computing",
        "quantum", "physics", "relativity", "thermodynamics", "gravity", "entropy",
        "speed of light", "astrophysics", "molecular", "dna", "computation",
        "reasoning", "logic deduction", "hypothesis", "complexity", "matrix",
        "eigenvalue", "photosynthesis", "cellular", "scientific mechanism"
    ]
    has_tech_u = any(tc in u_lower for tc in tech_robotics_cues)
    thinking_r_cues = [
        "computing", "calculating", "analyzing", "the algorithm indicates",
        "neural architecture", "processing data", "computation", "quantum mechanics",
        "mathematically", "laws of physics", "under the hood, my code",
        "the data indicates", "analyzing the logic"
    ]
    if is_math_query or has_tech_u or any(tr in r_lower for tr in thinking_r_cues):
        return ("thinking", "ANALYZING // THINKING")

    # 15. Mobility & Locomotion Inquiries (Moving expression showcase)
    is_locomotion_move = (
        bool(re.search(r"\b(can you|do you|able to|how do you)\s+move\b", u_lower))
        or bool(re.search(r"\bmove\s+(around|forward|backward|across|your body)\b", u_lower))
    )
    moving_u_cues = [
        "drive", "driving", "chassis", "wheels", "locomotion", "can you drive",
        "can you walk", "do you walk", "motor", "motors"
    ]
    moving_r_cues = [
        "mid-2027", "locomotion", "physical chassis", "motor pipeline", "lidar"
    ]
    if "move on" not in u_lower or any(mc in u_lower for mc in ["chassis", "motor", "wheels", "drive", "locomotion"]):
        if is_locomotion_move or any(mu in u_lower for mu in moving_u_cues) or any(mr in r_lower for mr in moving_r_cues):
            return ("moving", "LOCOMOTION // MID-2027 ROADMAP")

    # 16. Camera Vision / Optical Inspection (Watching)
    watching_u_cues = [
        "camera", "what do you see", "can you see me", "can you see what",
        "what am i holding", "what am i wearing", "look at this object",
        "look at what i'm", "look at what im", "viewfinder", "optical sensor",
        "camera lens", "inspect this", "inspect what"
    ]
    watching_r_cues = [
        "optical analysis", "inspecting", "viewfinder", "i see you", "you are holding",
        "you are wearing", "optical sensors indicate", "optical reticle active",
        "camera lens sees"
    ]
    if any(wu in u_lower for wu in watching_u_cues) or any(wr in r_lower for wr in watching_r_cues):
        return ("watching", "OPTICAL SENSORS // WATCHING")

    # 17. Inquisitive User Uncertainty / Undecided Visitor / Suggestions / Exploration / Questions (Curious)
    has_explanatory_question = bool(re.search(
        r"\b(why\s+(is|are|do|does|did)|how\s+(does|do|did|can|come)|what\s+(is|are|causes|happens|makes)|can\s+you\s+explain|tell\s+me\s+more|wondering|i\s+wonder)\b",
        u_lower
    ))
    curious_u_cues = [
        "what if", "i wonder", "curious about", "what's the difference",
        "what else", "what do you recommend", "tell me about", "what's next",
        "what should we do", "i'm curious", "im curious", "curious to know",
        "what happens when", "let's explore", "lets explore", "suggest something",
        "any suggestions"
    ]
    curious_r_cues = [
        "what would you like", "where should we start", "what do you think",
        "what's your pick", "which one", "what sounds most interesting",
        "what's on your mind", "what would you prefer", "shall we",
        "would you like to explore", "what shall we test", "what do you want to explore"
    ]
    if (
        is_uncertain_user_input(u_raw)
        or is_start_demonstration_inquiry(u_raw)
        or has_explanatory_question
        or any(cu in u_lower for cu in curious_u_cues)
        or any(cr in r_lower for cr in curious_r_cues)
        or r_raw.strip().endswith("?")
    ):
        return ("curious", "INQUISITIVE // CURIOUS")

    # 18. Casual Agreement / Banter / Compliments / Swag (Cool)
    is_cool_acknowledgment = bool(
        re.search(r"\b(that'?s|looks?|sounds?|pretty|very|so|super|really|stay)\s+cool\b", u_lower)
        or re.search(r"\byou('re|\s+are)?\s+(so\s+|pretty\s+|really\s+)?cool\b", u_lower)
        or re.search(r"^(cool|very cool|pretty cool|so cool|cool bro)\b", u_lower.strip())
    )
    cool_u_cues = [
        "cool bro", "swag", "chill", "stay cool", "smooth", "dope", "rad",
        "awesome bro", "nice one", "thats sweet", "that's sweet", "sweet!",
        "great job", "nice work", "well done", "impressive", "good job",
        "sounds good", "got it", "okay got it", "alright got it", "looking sharp",
        "sharp", "stylish", "stay chill", "no worries", "no problem",
        "fair enough", "all good", "you bet", "rock on", "slick"
    ]
    cool_r_cues = [
        "cool as always", "smooth sailing", "got you covered", "chill", "no sweat",
        "easy peasy", "with style", "rock and roll", "looking sharp", "stay cool",
        "you got style", "right on!", "all set", "stay frosty"
    ]
    if is_standalone_acknowledgment(u_raw) or is_cool_acknowledgment or any(cu in u_lower for cu in cool_u_cues) or any(cr in r_lower for cr in cool_r_cues):
        return ("cool", "CHILL // COOL")

    # 19. Friendly Baseline (Happy)
    return ("happy", "READY // TALK TO ME")

