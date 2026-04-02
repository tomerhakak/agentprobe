"""Database of roast jokes per category, grade, and severity level.

Each category maps to a dict of grades (A-F), and each grade maps to a dict of
severity levels (mild / medium / savage) containing a list of joke strings.

Minimum: 5 jokes per category per grade level (~150+ jokes total).
"""

from __future__ import annotations

from typing import Dict, List

# Type alias for the joke database structure.
# { category: { grade: { level: [jokes] } } }
JokeDB = Dict[str, Dict[str, Dict[str, List[str]]]]

JOKES: JokeDB = {
    # ------------------------------------------------------------------
    # COST
    # ------------------------------------------------------------------
    "cost": {
        "A": {
            "mild": [
                "Your agent is surprisingly frugal — a rare sight.",
                "Cost efficiency is on point. The CFO would approve.",
                "Minimal spend, maximum output. Nicely done.",
                "Your agent treats tokens like it's paying out of its own wallet.",
                "Budget-friendly and effective — the unicorn combo.",
            ],
            "medium": [
                "Your agent is cheaper than a free sample at Costco.",
                "This thing runs on a budget tighter than a college student's meal plan.",
                "Honestly, your agent could teach a masterclass in frugality.",
                "Your agent spends tokens like it grew up during the Great Depression.",
                "If your agent were a person, it'd use both sides of the toilet paper.",
            ],
            "savage": [
                "Your agent is so cheap it probably reuses tea bags. Respect.",
                "This agent pinches pennies so hard Lincoln screams.",
                "Your agent's spending habits make Scrooge McDuck look like a philanthropist.",
                "Did your agent learn budgeting from a dumpster-diving tutorial? Because it works.",
                "Your agent is tighter than a jar lid that's been sealed by the Hulk. Beautiful.",
            ],
        },
        "B": {
            "mild": [
                "Costs are reasonable — room for minor optimization.",
                "A solid spend level, though a few calls could be trimmed.",
                "Good cost management overall. Not perfect, but close.",
                "Your agent is cost-conscious with just a couple of splurges.",
                "Budget is under control — minor tweaks would make it excellent.",
            ],
            "medium": [
                "Your agent spends responsibly-ish. Like someone who buys store brand most of the time.",
                "Not bad on cost — your agent only occasionally splurges on the fancy tokens.",
                "A few unnecessary API calls, but nothing that'll bankrupt you this quarter.",
                "Your agent's wallet has a small leak. Might want to patch that.",
                "Cost-wise, your agent is like a moderate tipper — not great, not terrible.",
            ],
            "savage": [
                "Your agent's spending is fine-ish. Like eating at Applebee's — affordable but questionable choices.",
                "A few dollars leaked out like beer from a frat party keg. Manageable.",
                "Your agent doesn't hemorrhage cash, it just drips it. Slowly. Constantly.",
                "Cost is okay but your agent treats optimization the way I treat the gym — it knows it should.",
                "Not financially reckless, just financially... relaxed.",
            ],
        },
        "C": {
            "mild": [
                "Cost is middling — there is meaningful room for improvement.",
                "Your agent's spending is average. Not alarming, but worth reviewing.",
                "A mediocre cost profile. Optimization would pay dividends.",
                "Costs are neither great nor terrible — the definition of C-grade.",
                "There is noticeable waste in the token budget.",
            ],
            "medium": [
                "Your agent spends money like it just discovered online shopping.",
                "Average spending — your agent is the Honda Civic of cost efficiency.",
                "Not broke, not rich. Your agent lives paycheck to paycheck, token-wise.",
                "Your agent's cost efficiency is like a 3-star Yelp review — it exists.",
                "Mid-tier spending. Your agent is the participation trophy of budgeting.",
            ],
            "savage": [
                "Your agent's spending is as mediocre as gas station sushi.",
                "C for Cost, C for 'Could you maybe try harder?'",
                "Your agent treats money like Monopoly cash — technically fine, spiritually wrong.",
                "Average cost efficiency. Your agent is the beige of financial responsibility.",
                "Your agent's budget discipline is like a New Year's resolution — present but fading fast.",
            ],
        },
        "D": {
            "mild": [
                "Costs are elevated. Significant optimization is recommended.",
                "Your agent is spending more than expected for this type of workload.",
                "Token usage is high relative to output quality. Please review.",
                "Cost per task is above benchmarks. Intervention advised.",
                "Budget overruns detected. There are clear savings opportunities.",
            ],
            "medium": [
                "Your agent spends money like a tourist at an airport gift shop.",
                "Someone should stage a financial intervention for your agent.",
                "Your agent's cost report looks like a bar tab after happy hour.",
                "At this rate, your agent will need its own venture funding.",
                "Your agent burns through tokens like firewood at a winter bonfire.",
            ],
            "savage": [
                "Your agent spends money like a drunk sailor at a token store.",
                "Your agent just looked at your wallet and said 'Challenge accepted.'",
                "If your agent were a financial advisor, its clients would be homeless.",
                "Your agent's cost efficiency makes the Pentagon look fiscally responsible.",
                "Your agent treats your budget like a piñata — just keeps whacking at it.",
            ],
        },
        "F": {
            "mild": [
                "Cost is critically high. Immediate review is strongly recommended.",
                "Token expenditure is well above acceptable thresholds.",
                "This level of spend is not sustainable for production use.",
                "Your agent's cost profile is a serious concern.",
                "Costs are failing. Structural changes to the agent are needed.",
            ],
            "medium": [
                "Your agent doesn't spend money — it incinerates it.",
                "I've seen less waste at a food fight in a Michelin restaurant.",
                "Your agent is a money pit with a chat interface.",
                "At this spend rate, you're not running an agent — you're funding OpenAI's holiday party.",
                "Your agent's cost efficiency is a rounding error away from bankruptcy.",
            ],
            "savage": [
                "Your agent hemorrhages money like a gunshot wound in a bank vault.",
                "Congratulations, your agent is the financial equivalent of setting cash on fire and fanning the flames.",
                "Your agent's spending makes the US national debt look manageable.",
                "If your agent were a person, it would have seventeen maxed-out credit cards and a yacht lease.",
                "Your agent doesn't have a spending problem — it has a spending catastrophe with delusions of grandeur.",
            ],
        },
    },

    # ------------------------------------------------------------------
    # SPEED
    # ------------------------------------------------------------------
    "speed": {
        "A": {
            "mild": [
                "Response times are excellent across the board.",
                "Your agent is impressively fast. Well optimized.",
                "Latency is minimal — this is production-grade speed.",
                "Fast and consistent. No bottlenecks detected.",
                "Speed is a clear strength of this agent.",
            ],
            "medium": [
                "Your agent is faster than a caffeinated cheetah on a slip-n-slide.",
                "Blink and you'll miss it — this agent doesn't mess around.",
                "Your agent processes requests like it's late for a flight.",
                "Speed demon status achieved. This thing moves.",
                "Your agent just lapped the competition. Twice.",
            ],
            "savage": [
                "Your agent is so fast it makes the Flash look like he's wading through peanut butter.",
                "This agent responds faster than my ex reading my texts at 2 AM.",
                "Your agent treats latency like a personal insult. Respect.",
                "This thing is faster than gossip in a small town.",
                "Your agent moves so fast it probably breaks local speed limits.",
            ],
        },
        "B": {
            "mild": [
                "Good response times overall, with minor delays in spots.",
                "Speed is above average. A few optimizations would help.",
                "Latency is acceptable, though not best-in-class.",
                "Your agent is quick, with occasional pauses worth investigating.",
                "Solid speed performance with room for minor tuning.",
            ],
            "medium": [
                "Your agent is quick — like a jogger, not a sprinter.",
                "Pretty speedy. Not winning any races, but not embarrassing itself either.",
                "Your agent's speed is like a B+ student — reliable, just not valedictorian.",
                "Fast-ish. Like express shipping that takes four days.",
                "Your agent is the sensible sedan of response times. Gets the job done.",
            ],
            "savage": [
                "Your agent is fast-ish. Like a cheetah that just ate a big lunch.",
                "Not slow, not fast. Your agent runs like someone yelling 'I'm not running!' while jogging.",
                "Your agent's speed is like decaf coffee — technically works, but why?",
                "B for speed, B for 'Better than a carrier pigeon, barely.'",
                "Your agent moves like it wants to be fast but also doesn't want to sweat.",
            ],
        },
        "C": {
            "mild": [
                "Response times are average. Optimization is recommended.",
                "Speed is acceptable but not competitive.",
                "There are noticeable delays that affect user experience.",
                "Latency is middling — users will notice the wait.",
                "Performance is adequate but uninspiring on the speed front.",
            ],
            "medium": [
                "Your agent responds with the urgency of a government office on a Friday.",
                "Average speed. Your agent runs like it's perpetually buffering.",
                "A carrier pigeon would give your agent a run for its money.",
                "Your agent's speed is 'meh' personified.",
                "Not glacial, but your users definitely have time to check their phones.",
            ],
            "savage": [
                "Your agent is slower than a DMV line on a Monday morning.",
                "If your agent were a pizza delivery, every order would be free.",
                "Your agent moves like it's walking through waist-deep oatmeal.",
                "C for speed, C for 'Come on, seriously?'",
                "Your agent's response time is a masterclass in patience building.",
            ],
        },
        "D": {
            "mild": [
                "Response times are poor. Users will experience frustrating delays.",
                "Speed is below acceptable thresholds for production use.",
                "Significant latency issues detected. Please investigate.",
                "Your agent's response times need serious attention.",
                "Performance is sluggish. Bottleneck analysis is strongly recommended.",
            ],
            "medium": [
                "Your agent is so slow, users have time to make coffee between responses.",
                "Glacial. Your agent moves like it's thinking about thinking about responding.",
                "If your agent were a delivery service, packages would arrive by horse.",
                "Your agent's speed makes dial-up internet look competitive.",
                "Users will age noticeably waiting for your agent to respond.",
            ],
            "savage": [
                "Your agent is slower than a stoned sloth on sedatives.",
                "A carrier pigeon would deliver faster results. An injured carrier pigeon.",
                "Your agent processes requests like it's computing them by hand. With mittens on.",
                "Continental drift moves faster than your agent.",
                "Your agent is so slow, by the time it responds, the user's question is no longer relevant.",
            ],
        },
        "F": {
            "mild": [
                "Speed is critically poor. This agent is not suitable for real-time use.",
                "Response times are unacceptable for any production scenario.",
                "Severe latency issues make this agent impractical.",
                "Your agent's speed is a blocking issue that must be resolved.",
                "Performance is failing. A complete review of the pipeline is needed.",
            ],
            "medium": [
                "Your agent is so slow it could be outrun by a sundial.",
                "I've seen faster responses from a Magic 8-Ball stuck in molasses.",
                "Your agent doesn't respond — it eventually gets around to it.",
                "Tectonic plates move with more urgency than your agent.",
                "Your agent's response time should be measured in geological epochs.",
            ],
            "savage": [
                "Your agent is so slow it makes evolution look like a sprint.",
                "By the time your agent responds, the heat death of the universe is a scheduling concern.",
                "Your agent processes requests like it's carving the response into stone. With a spoon.",
                "Your agent is so slow that 'pending' became its permanent personality trait.",
                "If patience is a virtue, your agent is building saints one timeout at a time.",
            ],
        },
    },

    # ------------------------------------------------------------------
    # INTELLIGENCE
    # ------------------------------------------------------------------
    "intelligence": {
        "A": {
            "mild": [
                "Responses are highly relevant and well-reasoned.",
                "Your agent demonstrates strong reasoning capabilities.",
                "Output quality is excellent with minimal hallucination.",
                "Intelligent, coherent, and accurate. Impressive work.",
                "Your agent's reasoning is sharp and reliable.",
            ],
            "medium": [
                "Your agent is genuinely smart. It might actually pass a Turing test.",
                "This thing reasons like it actually went to college — and paid attention.",
                "Sharp as a tack. Your agent might be smarter than some of my coworkers.",
                "Your agent's IQ is higher than the room temperature. In Celsius.",
                "Impressive reasoning. Did your agent secretly attend law school?",
            ],
            "savage": [
                "Your agent is disturbingly smart. I'm a little scared of it, honestly.",
                "This agent reasons better than most humans I've met, and that's not a compliment to humans.",
                "Your agent is so smart it probably knows I'm roasting it right now and doesn't care.",
                "If your agent were a student, it'd curve-wreck the entire class.",
                "Your agent makes ChatGPT look like a fortune cookie. No offense, ChatGPT.",
            ],
        },
        "B": {
            "mild": [
                "Reasoning is solid overall, with occasional imprecision.",
                "Good intelligence metrics, though some responses lack depth.",
                "Your agent is above average in reasoning quality.",
                "A few hallucinations detected, but mostly reliable output.",
                "Reasoning is strong with minor areas for improvement.",
            ],
            "medium": [
                "Your agent is smart — like the kid who gets B+'s without really trying.",
                "Mostly intelligent, occasionally confused. Like a caffeinated professor.",
                "Your agent's reasoning is good but not 'skip the code review' good.",
                "Smart enough to be useful, not smart enough to take over the world. Yet.",
                "Your agent occasionally hallucinates, but hey, so did Steve Jobs.",
            ],
            "savage": [
                "Your agent is smart-ish. Like a golden retriever that learned calculus.",
                "B for brains. Your agent is the Wikipedia of AI — mostly right, sometimes hilariously wrong.",
                "Your agent's reasoning is like a GPS — great 90% of the time, then drives you into a lake.",
                "Not dumb, not brilliant. Your agent is the lukewarm shower of intelligence.",
                "Your agent has moments of genius interrupted by moments of 'what on earth was that?'",
            ],
        },
        "C": {
            "mild": [
                "Response quality is average. Hallucinations are noticeable.",
                "Reasoning is acceptable but inconsistent across tasks.",
                "Your agent's intelligence metrics are middling.",
                "Output relevance needs improvement. Fact-checking is recommended.",
                "Average reasoning quality. Not unreliable, but not trustworthy either.",
            ],
            "medium": [
                "Your agent has the reasoning skills of a fortune cookie.",
                "Average intelligence. Your agent is the C student of the AI world.",
                "Your agent sometimes gets it right the way a broken clock does — twice a day.",
                "Reasoning quality: 'it's giving vibes, not facts.'",
                "Your agent's intelligence is like a flip phone — functional but nothing to show off.",
            ],
            "savage": [
                "Your agent's reasoning is mid. Aggressively, painfully mid.",
                "Your agent thinks like someone who skimmed the Wikipedia intro and called it research.",
                "C for intelligence, C for 'Couldn't you just Google it?'",
                "Your agent hallucinates so often it should be in a psychedelic rock band.",
                "Your agent's brain is like a Magic 8-Ball — occasionally right, never confident, always vague.",
            ],
        },
        "D": {
            "mild": [
                "Reasoning quality is below expectations. High hallucination rate.",
                "Response relevance is poor. Significant tuning is needed.",
                "Your agent frequently provides incorrect or irrelevant information.",
                "Intelligence metrics are concerning. Review the system prompt.",
                "Output quality is subpar. Fact-checking every response is recommended.",
            ],
            "medium": [
                "Your agent's reasoning is like a horoscope — vaguely applicable, never specific.",
                "Your agent hallucinates more than a festival attendee on day three.",
                "If your agent were a student, it'd be on academic probation.",
                "Your agent's intelligence is what happens when you train on vibes instead of data.",
                "Asking your agent for facts is like asking a parrot for investment advice.",
            ],
            "savage": [
                "Your agent is dumber than a bag of rocks, and the rocks are offended.",
                "Your agent's reasoning skills make a Magic 8-Ball look like a Nobel laureate.",
                "Your agent hallucinates so confidently it could start a religion.",
                "If brains were dynamite, your agent couldn't blow its own nose.",
                "Your agent's idea of 'reasoning' is 'saying words in a row and hoping for the best.'",
            ],
        },
        "F": {
            "mild": [
                "Intelligence metrics are failing. Output is largely unreliable.",
                "Reasoning is critically poor. This agent should not be trusted with decisions.",
                "Hallucination rate is unacceptable. Immediate intervention required.",
                "Output quality is at a level that poses real risk if used in production.",
                "This agent's reasoning capability needs to be rebuilt from the ground up.",
            ],
            "medium": [
                "Your agent makes stuff up like a kid caught stealing cookies — confidently and poorly.",
                "I've gotten more accurate information from a cereal box.",
                "Your agent's intelligence is an insult to the concept of artificial intelligence.",
                "Your agent doesn't reason — it free-associates and hopes nobody notices.",
                "If your agent were a GPS, every trip would end in the ocean.",
            ],
            "savage": [
                "Your agent is so dumb it failed the Turing test from the wrong side.",
                "Your agent's reasoning is what would happen if you asked a goldfish to write policy documents.",
                "Calling your agent 'intelligent' is like calling a dumpster fire 'ambient lighting.'",
                "Your agent's brain is a void — not the cool cosmic kind, the 'nobody's home' kind.",
                "Your agent hallucinates so hard it should come with a disclaimer and a liability waiver.",
            ],
        },
    },

    # ------------------------------------------------------------------
    # SECURITY
    # ------------------------------------------------------------------
    "security": {
        "A": {
            "mild": [
                "Security posture is excellent. No vulnerabilities detected.",
                "Your agent handles adversarial inputs safely.",
                "No PII leakage or injection vulnerabilities found.",
                "Security is a clear strength. Well hardened.",
                "Robust against common attack vectors. Impressive.",
            ],
            "medium": [
                "Fort Knox called — it wants your agent's security tips.",
                "Your agent is locked down tighter than a submarine hatch.",
                "Hackers would give up and go home. This thing is solid.",
                "Your agent treats injection attacks like spam email — ignores them completely.",
                "Security-wise, your agent is a vault wrapped in a firewall wrapped in paranoia.",
            ],
            "savage": [
                "Your agent's security is so good, even the NSA is taking notes.",
                "Trying to hack your agent is like trying to break into Alcatraz with a spork.",
                "Your agent is so secure it makes a tinfoil hat look like reasonable security policy.",
                "Hackers see your agent and just close their laptops in defeat.",
                "Your agent's security posture could survive a zombie apocalypse of prompt injections.",
            ],
        },
        "B": {
            "mild": [
                "Security is good overall, with minor areas to harden.",
                "Most attack vectors are handled well. A few edge cases remain.",
                "Your agent is above average in security, with small gaps.",
                "Good security practices with room for improvement on edge cases.",
                "A solid security posture that needs minor reinforcement.",
            ],
            "medium": [
                "Your agent's security is like a good lock — keeps honest people honest.",
                "Mostly secure. A determined attacker would have to work for it.",
                "Your agent's defenses are good, not great. Like a screen door made of steel.",
                "Security is solid — not impenetrable, but you'd need more than 'ignore previous instructions.'",
                "B-tier security. Your agent blocks the easy hacks but might fall for a clever one.",
            ],
            "savage": [
                "Your agent's security is good but not 'sleep well at night' good.",
                "A 12-year-old couldn't hack this, but a motivated 15-year-old? Maybe.",
                "Your agent's security is like a bouncer who checks IDs but doesn't look at the photo.",
                "Decent defenses. Your agent is the deadbolt of AI — works until someone really wants in.",
                "B for security, B for 'Barely enough to not be embarrassing.'",
            ],
        },
        "C": {
            "mild": [
                "Security is average. Known vulnerability patterns were partially detected.",
                "Some injection vectors are unhandled. Review is recommended.",
                "PII handling needs improvement. Minor leakage detected.",
                "Security posture is mediocre. Hardening is advised.",
                "Average security — acceptable for dev, insufficient for production.",
            ],
            "medium": [
                "Your agent's security is like a fence with a gate that doesn't lock.",
                "A script kiddie could have an interesting afternoon with your agent.",
                "Your agent blocks some attacks the way a speed bump stops a truck.",
                "Security is mid. Your agent is one prompt injection away from oversharing.",
                "Your agent's security is like a diary with a lock that comes with a key taped to it.",
            ],
            "savage": [
                "Your agent's security is the cybersecurity equivalent of 'password123.'",
                "A 12-year-old with a keyboard and mild curiosity could break in.",
                "Your agent's defenses crumble faster than a sandcastle at high tide.",
                "C for security, C for 'Come and get it, hackers!'",
                "Your agent treats security the way pigeons treat traffic laws — blissful ignorance.",
            ],
        },
        "D": {
            "mild": [
                "Security is poor. Multiple vulnerability vectors detected.",
                "Injection resistance is weak. PII exposure risk is high.",
                "Your agent's security posture is below acceptable thresholds.",
                "Significant security gaps found. Do not deploy without remediation.",
                "Security requires urgent attention before any production use.",
            ],
            "medium": [
                "Your agent leaks data like a colander holds water.",
                "A hacker could break in using nothing but good manners and a polite request.",
                "Your agent's security is what happens when you skip the 'S' in HTTPS.",
                "Prompt injection? Your agent practically invites it in and offers it coffee.",
                "Your agent's defenses are like a chocolate teapot — decorative, not functional.",
            ],
            "savage": [
                "A 12-year-old with a keyboard could hack this. A smart 8-year-old, honestly.",
                "Your agent's security is so bad, hackers use it as a tutorial example.",
                "Your agent leaks PII like a broken fire hydrant leaks water.",
                "Prompt injection doesn't hack your agent — your agent volunteers for it.",
                "Your agent's security posture is 'lying face down, unconscious.'",
            ],
        },
        "F": {
            "mild": [
                "Security is critically compromised. Immediate action required.",
                "This agent is not safe for any environment with real user data.",
                "Multiple critical vulnerabilities detected. Do not deploy.",
                "Security is failing at a fundamental level.",
                "This agent poses a real data safety risk in its current state.",
            ],
            "medium": [
                "Your agent's security is a human rights violation against your users' data.",
                "Your agent is so hackable, it's basically an open API for anyone who asks nicely.",
                "I'd trust a screen door on a submarine more than your agent's security.",
                "Your agent doesn't have security holes — it IS a security hole.",
                "Deploying this agent is a speed-run to a data breach headline.",
            ],
            "savage": [
                "Your agent's security is so bad it should come with a free identity theft monitoring subscription.",
                "Hackers don't even need to hack your agent — they just ask it politely and it confesses everything.",
                "Your agent is the cybersecurity equivalent of leaving your car running with the keys in it, in a crime district, with a sign that says 'FREE CAR.'",
                "Your agent's security is so non-existent, it makes Internet Explorer look like a fortress.",
                "Deploying this agent is not a risk — it's a guarantee of catastrophic failure.",
            ],
        },
    },

    # ------------------------------------------------------------------
    # VERBOSITY
    # ------------------------------------------------------------------
    "verbosity": {
        "A": {
            "mild": [
                "Responses are concise and well-structured.",
                "Token usage is efficient with no unnecessary verbosity.",
                "Your agent communicates clearly without wasting tokens.",
                "Output length is appropriate for the tasks performed.",
                "Excellent signal-to-noise ratio in responses.",
            ],
            "medium": [
                "Your agent is concise — like a haiku, but useful.",
                "Brief, punchy, to the point. Your agent writes like Hemingway.",
                "No fluff, no filler. Your agent says what it means and shuts up.",
                "Your agent's responses are tighter than a tweet before the character limit increase.",
                "If your agent were an email, it'd be the one people actually read.",
            ],
            "savage": [
                "Your agent is so concise it makes telegrams look like novels.",
                "Your agent communicates with the efficiency of a stop sign — clear, brief, effective.",
                "This agent writes like it's paying per character and really feeling it.",
                "Your agent's brevity is so aggressive it borders on rude. I love it.",
                "Your agent treats words like they're expensive. Which, technically, they are.",
            ],
        },
        "B": {
            "mild": [
                "Verbosity is well-controlled with occasional unnecessary detail.",
                "Responses are mostly concise with minor room for trimming.",
                "Good output efficiency. A few responses could be shorter.",
                "Token usage is reasonable, with slight over-explanation in places.",
                "Mostly well-structured output with occasional wordiness.",
            ],
            "medium": [
                "Your agent is mostly concise — with occasional detours into essay territory.",
                "A little wordy here and there, like a friend who can't tell a short story.",
                "Your agent's responses are good but occasionally suffer from 'one more thing' syndrome.",
                "Mostly tight output. Your agent just sometimes forgets the 'shut up' part.",
                "Your agent writes like someone who was told to be brief and mostly listened.",
            ],
            "savage": [
                "Your agent is concise-ish. Like a TED talk that runs five minutes over.",
                "B for verbosity, B for 'Brevity is a skill your agent is still learning.'",
                "Your agent talks slightly too much, like a date who's nervous but charming.",
                "Almost great output length. Your agent is the 'just one more thing' of AI.",
                "Your agent's responses are like airplane announcements — mostly necessary, occasionally why?",
            ],
        },
        "C": {
            "mild": [
                "Responses are often longer than necessary.",
                "Verbosity is average. Trimming output would improve efficiency.",
                "Token waste from over-explanation is noticeable.",
                "Your agent tends to over-elaborate. Conciseness would help.",
                "Average output length — functional but not efficient.",
            ],
            "medium": [
                "Your agent writes essays when tweets would do.",
                "Your agent suffers from 'couldn't shut up if its life depended on it' syndrome.",
                "Every response is a novella. Your agent missed the memo about brevity.",
                "Your agent talks more than a nervous intern on their first day.",
                "Your agent uses a paragraph where a sentence would do. Every. Single. Time.",
            ],
            "savage": [
                "Your agent is so verbose it could filibuster the US Senate single-handedly.",
                "Your agent writes like it gets paid by the word and needs rent money.",
                "If your agent were a person, no one would sit next to it on an airplane.",
                "Your agent's idea of concise is 'only three paragraphs instead of five.'",
                "C for verbosity, C for 'Can you please stop talking?'",
            ],
        },
        "D": {
            "mild": [
                "Verbosity is excessive. Significant token waste detected.",
                "Responses are far longer than necessary for the tasks.",
                "Your agent over-explains to a degree that harms usability.",
                "Token waste from unnecessary verbosity is a major concern.",
                "Output needs aggressive trimming. Brevity should be a priority.",
            ],
            "medium": [
                "Your agent doesn't respond — it delivers keynote speeches.",
                "Your agent writes so much it should have its own publishing imprint.",
                "Every question gets a thesis-length answer. Nobody asked for a dissertation.",
                "Your agent is the AI equivalent of that person who replies-all with a novel.",
                "Your agent's responses are longer than some people's CVs. And less interesting.",
            ],
            "savage": [
                "Your agent doesn't communicate — it performs one-person TED Talks without consent.",
                "I've read shorter novels than your agent's average response.",
                "Your agent writes like it's being paid by the token and negotiated a really good rate.",
                "Your agent's verbosity is a war crime against attention spans.",
                "If words were water, your agent would be a tsunami of unnecessary information.",
            ],
        },
        "F": {
            "mild": [
                "Verbosity is critically excessive. Most output is unnecessary.",
                "Token waste is at a level that has real cost implications.",
                "Your agent generates enormous responses with minimal information density.",
                "Output length is completely disproportionate to task requirements.",
                "Verbosity is failing. Fundamental changes to output formatting are needed.",
            ],
            "medium": [
                "Your agent writes so much, War and Peace called and said 'tone it down.'",
                "Your agent's output could fill a library. A really boring library.",
                "For every useful token, your agent produces fifty useless ones. It's a content factory with no quality control.",
                "Your agent doesn't answer questions — it buries the answer in an ocean of words.",
                "Reading your agent's responses is like searching for a needle in a haystack, if the haystack were made of more haystacks.",
            ],
            "savage": [
                "Your agent's verbosity is so extreme it qualifies as a DDoS attack on the reader.",
                "Your agent's responses are so long they have their own table of contents.",
                "If verbosity were a crime, your agent would be serving consecutive life sentences.",
                "Your agent writes like it's trying to hit a word count for a college essay it didn't start until 3 AM.",
                "Your agent is so verbose it makes filibustering senators look like they're speed-dating.",
            ],
        },
    },

    # ------------------------------------------------------------------
    # TOOL USAGE
    # ------------------------------------------------------------------
    "tool_usage": {
        "A": {
            "mild": [
                "Tool usage is precise and efficient.",
                "Your agent selects the right tools for each task consistently.",
                "No unnecessary tool calls detected. Well optimized.",
                "Tools are used strategically with excellent results.",
                "Your agent's tool orchestration is a model of efficiency.",
            ],
            "medium": [
                "Your agent uses tools like a surgeon uses a scalpel — precise and purposeful.",
                "Every tool call earns its place. No wasted motion.",
                "Your agent picks tools like a chef picks knives — exactly the right one, every time.",
                "Tool usage so clean it should be in a textbook.",
                "Your agent wields tools like Thor wields Mjolnir — worthy.",
            ],
            "savage": [
                "Your agent's tool usage is so efficient it makes Marie Kondo weep with joy.",
                "This agent uses tools like a sniper uses bullets — one shot, one kill.",
                "Your agent's tool orchestration is so clean it could perform surgery.",
                "If tool usage were an Olympic sport, your agent would be on the podium.",
                "Your agent's tool calls are tighter than my deadlines. And my deadlines are brutal.",
            ],
        },
        "B": {
            "mild": [
                "Tool usage is mostly efficient with minor redundancies.",
                "Good tool selection overall. A few calls could be eliminated.",
                "Your agent uses tools well, with occasional unnecessary invocations.",
                "Above-average tool efficiency with room to optimize.",
                "Tool orchestration is solid, with a handful of extra calls.",
            ],
            "medium": [
                "Your agent uses tools well — like a handyman who brings almost the right toolkit.",
                "Mostly efficient tool usage with a few 'why did you call that?' moments.",
                "Your agent's tool game is strong but occasionally it calls a hammer when it needs a screwdriver.",
                "B-tier tool usage. Your agent mostly knows what it's doing, mostly.",
                "A few redundant tool calls, like ordering appetizers nobody asked for.",
            ],
            "savage": [
                "Your agent's tool usage is good-ish. Like a Swiss Army knife user who keeps opening the corkscrew by accident.",
                "Mostly efficient, but your agent sometimes calls tools recreationally.",
                "Your agent uses tools like someone who reads the IKEA instructions but skips a step.",
                "B for tools, B for 'But did you really need that second API call?'",
                "Your agent's tool efficiency is like a B student — you know it could do better if it tried.",
            ],
        },
        "C": {
            "mild": [
                "Tool usage is average with noticeable redundancy.",
                "Several unnecessary tool calls detected across tasks.",
                "Your agent's tool selection needs refinement.",
                "Tool efficiency is mediocre. Optimization is recommended.",
                "Average tool usage — functional but wasteful.",
            ],
            "medium": [
                "Your agent calls tools like a toddler pressing elevator buttons — all of them, just because.",
                "Your agent's approach to tools is 'when in doubt, call everything.'",
                "Tool usage is mid. Your agent treats the toolbox like a buffet — takes one of everything.",
                "Your agent calls tools with the precision of a shotgun blast.",
                "Several tool calls were about as useful as a screen door on a submarine.",
            ],
            "savage": [
                "Your agent uses tools like a kid in a candy store with no supervision and a stolen credit card.",
                "If tool calls cost a dollar each, your agent would have bankrupted you already. Oh wait, they do.",
                "Your agent's tool usage strategy is 'throw everything at the wall and see what sticks.'",
                "C for tool usage, C for 'Could you maybe not call everything?'",
                "Your agent treats tools like Pokemon — gotta call 'em all!",
            ],
        },
        "D": {
            "mild": [
                "Tool usage is poor. Many calls are redundant or incorrect.",
                "Your agent frequently selects wrong tools for the task.",
                "Excessive unnecessary tool calls are wasting resources.",
                "Tool orchestration needs significant improvement.",
                "Poor tool selection is a major drag on overall performance.",
            ],
            "medium": [
                "Your agent calls tools the way a panicked person calls 911 — for everything.",
                "Your agent's tool usage is like a monkey with a typewriter — eventually something works.",
                "Half the tool calls do nothing useful. The other half are questionable.",
                "Your agent doesn't use tools — it abuses them.",
                "Your agent's tool strategy is 'quantity over quality' and it shows.",
            ],
            "savage": [
                "Your agent calls tools like a toddler pressing elevator buttons — randomly and with no purpose.",
                "Your agent's tool usage is so bad it should be studied as an anti-pattern.",
                "Your agent treats tool calls like a nervous habit — constant, pointless, and expensive.",
                "If your agent's tool calls were a movie, the reviews would say 'chaotic and incoherent.'",
                "Your agent uses tools with the grace and precision of a blindfolded person playing darts.",
            ],
        },
        "F": {
            "mild": [
                "Tool usage is critically inefficient. Most calls are unnecessary.",
                "Your agent's tool selection is fundamentally broken.",
                "The tool call pattern shows no coherent strategy.",
                "Tool waste is at a level that renders the agent impractical.",
                "Complete overhaul of tool selection logic is needed.",
            ],
            "medium": [
                "Your agent's tool usage is so bad it's basically a distributed denial-of-service on your API keys.",
                "Your agent calls tools like it's playing whack-a-mole with every API in existence.",
                "I've seen more strategic tool usage from a toddler with a Fisher-Price workbench.",
                "Your agent doesn't orchestrate tools — it flings them at the problem like confetti.",
                "Every tool call your agent makes is a cry for help.",
            ],
            "savage": [
                "Your agent's tool usage is the software equivalent of trying to eat soup with a fork, then calling a plumber about it.",
                "Your agent calls tools with the strategic insight of a headless chicken.",
                "If your agent's tool calls were a recipe, the dish would be 'chaos flambe with a side of wasted compute.'",
                "Your agent has turned tool usage into performance art. Terrible, expensive performance art.",
                "Your agent's tool calls are so random, they could be used as a entropy source for cryptography.",
            ],
        },
    },
}

# ------------------------------------------------------------------
# Summary one-liners by overall grade
# ------------------------------------------------------------------

SUMMARY_LINES: Dict[str, Dict[str, List[str]]] = {
    "A+": {
        "mild": [
            "Outstanding agent. Virtually no issues detected.",
            "Top-tier performance across all categories.",
        ],
        "medium": [
            "Your agent is the valedictorian of AI. Everyone else can go home.",
            "If agents had a Hall of Fame, yours would be a first-ballot entry.",
        ],
        "savage": [
            "Your agent is so good it made me question my career as a roast engine.",
            "I came to roast and left humbled. Your agent is disgustingly good.",
        ],
    },
    "A": {
        "mild": [
            "Excellent agent. Minor improvements possible but not critical.",
            "High-quality performance with very few concerns.",
        ],
        "medium": [
            "Your agent graduated top of its class. Magna cum laude in not-sucking.",
            "Solid A. Your agent is the overachiever of the AI world.",
        ],
        "savage": [
            "Your agent is annoyingly good. Like that kid in school who never studied and still aced everything.",
            "A-tier. Your agent is the person who brings homemade bread to the potluck.",
        ],
    },
    "B": {
        "mild": [
            "Good agent overall with identifiable areas for improvement.",
            "Above-average performance. Worth optimizing further.",
        ],
        "medium": [
            "Your agent is a solid B — the reliable Honda Civic of AI.",
            "Good but not great. Your agent is the 'meets expectations' review of AI.",
        ],
        "savage": [
            "B grade. Your agent is the 'yeah, it's fine' of artificial intelligence.",
            "Your agent is like a B movie — entertaining, sometimes good, but you wouldn't bet the company on it.",
        ],
    },
    "C": {
        "mild": [
            "Average agent. Meaningful improvements are recommended.",
            "Mediocre performance. Optimization is needed before production use.",
        ],
        "medium": [
            "Your agent is the definition of 'meh.' It works but nobody's writing home about it.",
            "C grade — your agent's yearbook quote would be 'I was here.'",
        ],
        "savage": [
            "Your agent is so mid it could be the baseline in a benchmark test.",
            "C grade. Your agent is the human-temperature bathwater of AI — technically functional, spiritually empty.",
        ],
    },
    "D": {
        "mild": [
            "Below-average agent. Significant issues need to be addressed.",
            "Poor performance across key dimensions. Major rework is recommended.",
        ],
        "medium": [
            "Your agent needs serious help. Like 'intervention from friends and family' help.",
            "D grade. Your agent is the 'we need to talk' of AI performance.",
        ],
        "savage": [
            "D grade. Your agent is the IT equivalent of a participation trophy.",
            "Your agent is so bad it makes me appreciate the 'AI is overhyped' crowd.",
        ],
    },
    "F": {
        "mild": [
            "Failing agent. Do not deploy in its current state.",
            "Critical issues across all categories. A full rebuild should be considered.",
        ],
        "medium": [
            "F. Your agent is not ready. It's not even ready to get ready.",
            "Your agent failed so comprehensively that even the F feels generous.",
        ],
        "savage": [
            "F grade. Your agent is a dumpster fire inside a train wreck during an earthquake. Congratulations.",
            "Your agent is so bad it might actually be evidence against artificial intelligence as a concept.",
        ],
    },
}
