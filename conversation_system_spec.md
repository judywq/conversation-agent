# Conversation System Specification 

## 1. Overview
This system implements a controlled multi-party discussion between one user and three AI agents.  
The system is governed by a **Turn Manager**, which determines both:
1. whether the conversation should terminate  
2. who should speak next  

All utterances are processed through a unified pipeline and stored in memory.

This system is delivered as a **web app** where the user can:
- log in and manage a profile
- speak into their microphone to contribute turns
- request a turn via a UI control
- see when each AI agent is speaking
- hear AI agents via voice playback

### Conversation System Flow
  
1. Initialization Phase

When the user lands on the page, they first enter a discussion topic.

The system then checks whether the user is a first-time user.

1.1 First-time users

If the user is new, they are required to create a profile consisting of:

Personality traits (OCEAN)
The user completes a self-evaluation using five statements corresponding to:

Openness
Conscientiousness
Extraversion
Agreeableness
Neuroticism

Each trait is rated on a coarse scale (e.g., high / medium / low).

Language proficiency (CEFR-aligned)
The user listens to short audio clips related to the discussion topic and selects the level that best matches their comprehension ability.

This information is stored as the user profile.

1.2 Returning users

If the user already has a profile, the system simply loads it.

1.3 Agent creation

After obtaining the user profile, the system creates three AI agents designed to complement the user.

Agents are selected or constructed such that they are strong in traits where the user is weaker
Each agent is assigned:
a personality profile
derived behavioral tendencies (e.g., leadership, supportiveness, skepticism)

These personality traits are then injected into the prompts used for later utterance generation.

1.4 Conversation state initialization

The system initializes the conversation state, including:

turn count = 0
memory (short-term and session) = empty
previous speaker = none
override flags = false
termination flag = false

Control is then passed to the Turn Manager.

2. Conversation Loop

The conversation proceeds in an iterative loop controlled entirely by the Turn Manager.

At each iteration, the Turn Manager performs:

1. Termination check
2. Next speaker selection
3. First Turn Logic

At the beginning of the discussion:

The system asks whether the user wants to speak first
Case A: User speaks first
The user provides input directly
This input does NOT go through the Facilitator
It is sent directly to the Turn Processor
Case B: User does not speak first
The Turn Manager selects the agent with the highest leadership trait
The system proceeds through the agent pipeline
4. Agent Turn Pipeline

When an agent is selected as the next speaker:

4.1 Facilitator planning

The Facilitator generates a structured instruction including:

Speech Act (SA type) — based on the five categories and subtypes
Target (who the utterance is addressing)
Content requirement
Retrieval requirement 

The Facilitator determines what kind of speech act should be made, not the wording.

4.2 Agent generation

The selected agent:

performs retrieval if required (memory / knowledge / etc.)
generates an utterance using:
its personality prompt
facilitator instruction
conversation context


5. User Turn Pipeline

When the user speaks (either voluntarily or after being selected):

The user produces raw input
The input bypasses the Facilitator
It is sent directly to the Turn Processor

6. Turn Processor (Core Module)

All utterances (agent, user, or makeshift) pass through the Turn Processor.

The Turn Processor performs:

6.1 Speech Act classification (for user utterance only)

By a fine-tuned LLM

6.2 State update
For agent utterance, copy metadata from facilitator, update turn counts, etc.
For user utterance, get metadata from 6.1, update turn counts, etc.



6.3 Memory update

The utterance is stored in:

short-term memory (recent context)
session memory (full conversation)

7. Turn Manager (Control Logic)

After the Turn Processor updates the state, control returns to the Turn Manager.

The Turn Manager decides the next speaker using rule-based logic, including:

Speech Act type
e.g., if SA = Directive and target is specific → target speaks next
Target
Turn counts / participation balance
Conversation flow constraints: appointment of an agent or user

If the target is “everyone”, fallback rules apply (e.g., least active speaker or role-based selection).

8. User Override Mechanism

a. At any time, the user can press a “raise hand” button.

This sets an override flag
The Turn Manager gives priority to the user in the next turn decision

b. The user is selected by the Turn Manager as the next speaker, then the previous speaker will become a makeshift speaker and speak again to appoint the user.
c. The user ends the discussion before the ending condition is met.

9. Continuation and Termination

At the start of each loop iteration:

The Turn Manager checks whether the conversation should terminate

If termination is true:

the conversation ends
no further speaker is assigned

Otherwise:

the next speaker is selected
the loop continues


### Conversation System Architecture

Here is a workflow diagram illustrating the system architecture:

```mermaid
flowchart TD

    S[User lands on page]
    AUTH{Authenticated?}
    LOGIN[Login / Sign up]
    DASH[Conversation UI]
    T[User enters discussion topic]
    N{User profile available?}

    P1[OCEAN self-evaluation]
    P2[CEFR-aligned audio selection]
    PS[Store user profile]

    LP[Load existing profile]

    AC[Create 3 complementary agents]
    PI[Inject agent personalities into prompts]

    INIT[Initialize conversation state]

    TM[Turn Manager: termination check and next speaker]

    END[End conversation]

    FTQ{First_turn_question:\nUser_speaks_first?}
    Q{Override_flag_set?\nRaise_hand_pressed}
    D{Next_speaker_selection}

    R[User requests to speak (UI button)]
    MIC[Microphone capture + speech-to-text]
    U[User input (transcript)]
    MS[Makeshift speaker: previous speaker invites user to speak]
    F[Facilitator plan: SA / subtype / target / content / retrieval]
    A[Agent utterance generation with retrieval]
    TTS[Text-to-speech]
    PLAY[Play agent voice audio]
    UISTAT[UI: agent speaking status]

    TP[Turn Processor: normalize / metadata / count / state update]
    M[Memory: short-term and session]

    %% initialization
    S --> AUTH
    AUTH -->|No| LOGIN --> AUTH
    AUTH -->|Yes| DASH --> T --> N

    N -->|No| P1
    P1 --> P2 --> PS --> AC
    N -->|Yes| LP --> AC

    AC --> PI --> INIT --> TM

    %% termination check
    TM -->|terminate = true| END

    %% first turn handling
    TM -->|continue and turn_count = 0| FTQ
    FTQ -->|Yes| R
    FTQ -->|No| D

    %% override can happen any time; it biases next selection to user
    TM -->|continue and turn_count > 0| Q
    Q -->|Yes| D
    Q -->|No| D

    D -->|next speaker = agent| F
    D -->|next speaker = user\n(volunteered)| R
    D -->|next speaker = user\n(appointed)| MS

    %% makeshift call to user
    MS --> TP --> M --> TM

    %% agent path
    F --> A --> UISTAT --> TTS --> PLAY --> TP

    %% user path
    R --> MIC --> U --> TP

    %% loop back
    M --> TM
 ```

---

## 2. Speech Act (SA) Framework

This system adopts the **literature-supported five speech act types** (Searle, 1976):

- **Assertives**: statements describing the world (e.g., informing, claiming)
- **Directives**: attempts to get someone to do something (e.g., asking, requesting)
- **Commissives**: committing to future action (e.g., promising)
- **Expressives**: expressing psychological states (e.g., thanking, apologizing)
- **Declarations**: changing the state of affairs (rare in this system)

The following is the type and subtype for speech acts:

Type	Subtype	Definition
ASSERTIVES	inform	Provide factual or contextual information
ASSERTIVES	opinion	Express a personal view or evaluation
ASSERTIVES	hypothesize	Propose a tentative idea or speculation
ASSERTIVES	confirm	Affirm or verify prior information (verifies truth / correctness of content)
DIRECTIVES	suggest	Propose a course of action
DIRECTIVES	request_info	Ask for new information
DIRECTIVES	request_confirm	Ask for confirmation/validation
DIRECTIVES	invite	Invite participation or contribution
DIRECTIVES	request_action	Ask someone to perform an action
DIRECTIVES	request_permission	Ask for permission to speak/act
COMMISSIVES	offer	Offer to do something
COMMISSIVES	promise	 Commit to a future action
COMMISSIVES	threaten	Commit to a negative consequence
EXPRESSIVES	agree	Show agreement
EXPRESSIVES	disagree	Express disagreement
EXPRESSIVES	acknowledge	Signal understanding or receipt (signals receipt / understanding / attention)
EXPRESSIVES	thank	Express gratitude
EXPRESSIVES	greet_welcome	Greet or welcome participants
EXPRESSIVES	apologize	Express apology
DECLARATIONS	open_session	Begin a session or activity
DECLARATIONS	assign_task	Assign work or responsibility
DECLARATIONS	close_session	End a session
DECLARATIONS	allocate_floor	Give speaking rights


---

## 3. Key Components

### 3.1 Turn Manager
Central controller.

Responsibilities:
- perform termination check
- decide next speaker

---

### 3.2 Facilitator
Used only for agent turns.

Outputs structured instruction:
- SA type
- target
- content requirement
- retrieval requirement

---

### 3.3 User
Human participant.

Characteristics:
- produces raw input
- does NOT go through Facilitator
- may volunteer or be appointed
- may provide input via microphone (speech-to-text) in the web app UI

---

### 3.4 Makeshift Speaker
The previous speaker re-used when:
- user is selected by the Turn Manager (non-volunteer)

Function:
- invite the user to speak

---

### 3.5 Agent
AI speaker.

Responsibilities:
- generate utterance based on:
  - Facilitator instruction
  - persona prompt
  - memory

---

### 3.6 Turn Processor
Post-turn processing module.

Responsibilities:
- normalize turn
- extract metadata for agents from Facilitator (SA, target, etc.)
- generate metadata for user
- update turn count
- update conversation state
- write to memory

---

### 3.7 Memory

#### Short-term memory
Recent turns for local coherence

#### Session memory
Full conversation history

### 3.8 User overrides
- User volunteers to speaker next or start the conversation
- User was appointed by the Turn Manager to be the next speaker
- User requests to end conversation before the prescribed ending condition.

---

## 4. Web Application Requirements

### 4.1 Authentication and profile management
- The system MUST support **user login** and **profile management** in the web UI.
- The system MUST persist the `UserProfile` per authenticated user, and load it on subsequent sessions.
- The system SHOULD support basic account actions (e.g., view/update profile fields, sign out).

### 4.2 Conversation UI
- The UI MUST provide a control for the user to **request speaking** (a button).
- When the user requests speaking, the UI MUST initiate **microphone capture** and produce a text transcript used as `User.input()`.
- The UI SHOULD provide clear states for microphone usage (idle, requesting permission, recording, transcribing, error).

### 4.3 Agent speaking status UI
- The UI MUST display **AI agent speaking status** (e.g., which agent is currently speaking, and/or queued).
- The UI SHOULD reflect transitions (thinking/generating, speaking/playing audio, finished).

### 4.4 Agent voice playback
- The system MUST support producing audible speech for agent utterances (text-to-speech).
- The UI MUST play the AI agent audio for the user.
- The system SHOULD allow selecting or mapping voices (e.g., aligned with profile or per-agent voice).
 
---

## 5. Data Structures

### UserProfile
```python
class UserProfile:
    ocean: dict[str, str]  # e.g., {"openness": "high", "conscientiousness": "medium", ...}
    cefr_level: str
    # web app identity linkage
    user_id: str
```

### AgentProfile
```python
class AgentProfile:
    id: str
    personality: dict
    traits: dict
```

### ConversationState
```python
class ConversationState:
    turn_count: int
    previous_speaker: str | None
    pending_forced_user_turn: bool
    terminate: bool
```

### TurnRecord
```python
class TurnRecord:
    speaker: str
    speaker_type: str
    utterance: str
    speech_act: str
    subtype: str | None
    target: str | None
    turn_index: int
    # web app / audio metadata (optional)
    source: str | None  # e.g., "mic", "text"
    audio_url: str | None  # agent audio asset location if generated
```

---

## 6. Core Loop

```python
while not state.terminate:

    if should_terminate(state):
        break

    # Turn Manager owns control flow:
    # - termination check
    # - next speaker selection (rule-based)
    # - first-turn logic (ask whether user speaks first)
    # - override handling (raise-hand flag biases next selection)
    speaker = decide_next_speaker(state)

    if speaker == "agent":
        plan = Facilitator(...)
        utterance = Agent.generate(plan)
        audio = TTS(utterance)
        UI.play(audio)

    elif speaker == "user":  # user utterance bypasses Facilitator
        utterance = User.input()

    elif speaker == "makeshift":  # used when user is appointed (non-volunteer)
        utterance = invite_user()  # previous speaker allocates the floor to user

    state = TurnProcessor(utterance, state)
    Memory.update(state)
```

---

## 7. Special Logic: Forced User Turn

If user is selected but did not volunteer:

1. Makeshift speaker produces invitation
2. Turn is processed
3. `pending_forced_user_turn = True`
4. Next turn → user is forced speaker

---

## 8. Termination

Handled only by Turn Manager.

Occurs when:
- max turns reached
- conversation converges
- inactivity or completion condition
