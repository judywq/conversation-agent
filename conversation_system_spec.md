# Conversation System Specification 

## 1. Overview
This system implements a controlled multi-party discussion between one user and three AI agents.  
The system is governed by a **Turn Manager**, which determines both:
1. whether the conversation should terminate  
2. who should speak next  

All utterances are processed through a unified pipeline and stored in memory.

Here is a workflow diagram illustrating the system architecture:

```mermaid
flowchart TD

    S[User lands on page]
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

    Q{User overrides: volunteering or appointed}
    D{Speaker selection}

    U[User input]
    MS[Makeshift speaker: previous speaker invites user to speak]
    F[Facilitator plan: SA / subtype / target / content / retrieval]
    A[Agent utterance generation with retrieval]

    TP[Turn Processor: normalize / metadata / count / state update]
    M[Memory: short-term and session]

    %% initialization
    S --> T --> N

    N -->|No| P1
    P1 --> P2 --> PS --> AC
    N -->|Yes| LP --> AC

    AC --> PI --> INIT --> TM

    %% termination check
    TM -->|terminate = true| END

    %% first turn handling
    TM -->|continue and turn_count = 0| Q

    Q -->|Yes| U
    Q -->|No| D

    D -->|next speaker = agent| F
    D -->|next speaker = user| MS

    %% makeshift call to user
    MS --> TP --> M --> TM

    %% agent path
    F --> A --> TP

    %% user path
    U --> TP

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

## 4. Data Structures

### UserProfile
```python
class UserProfile:
    ocean: dict[str, str]  # e.g., {"openness": "high", "conscientiousness": "medium", ...}
    cefr_level: str
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
```

---

## 5. Core Loop

```python
while not state.terminate:

    if should_terminate(state):
        break

    speaker = decide_next_speaker(state)

    if speaker == "agent":
        plan = Facilitator(...)
        utterance = Agent.generate(plan)

    elif speaker == "user":
        utterance = User.input()

    elif speaker == "makeshift":
        utterance = invite_user()

    state = TurnProcessor(utterance, state)
    Memory.update(state)
```

---

## 6. Special Logic: Forced User Turn

If user is selected but did not volunteer:

1. Makeshift speaker produces invitation
2. Turn is processed
3. `pending_forced_user_turn = True`
4. Next turn → user is forced speaker

---

## 7. Termination

Handled only by Turn Manager.

Occurs when:
- max turns reached
- conversation converges
- inactivity or completion condition
