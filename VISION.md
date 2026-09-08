# Clappy

> **Three phones. One script. No camera crew.**

Clappy is an AI director for small film crews.

The premise is simple: people already own excellent cameras. What low-budget filmmakers still lack is the crew around those cameras — someone coordinating them, following the script, deciding what should be on screen, keeping the take organized, and turning several simultaneous recordings into one usable scene.

Clappy turns a handful of phones into a coordinated multicamera production system.

This is not meant to be another AI video editor. The ambition is larger: **the screenplay becomes part of the camera crew.**

---

## The vision

A filmmaker loads a scene, places several phones around the actors, labels what each camera sees, and tells Clappy what kind of scene they are trying to make.

One phone might be Tom's close-up.  
Another might be Bella's close-up.  
A third might hold the wide.

Clappy understands the script, the characters, the beats of the scene, and the director's intent.

Then:

> “Clappy, roll.”

Every connected camera starts recording.

The raw footage stays intact on every device. Nothing is thrown away.

At the same time, Clappy follows the performance and builds a live multicamera cut. It knows who is speaking, where the actors are in the scene, what camera covers each person, what the current directing intent is, and what has already been shown.

The filmmaker can intervene naturally:

> “Stay on Bella after this.”  
> “Go wide after Tom's next line.”  
> “Hold the reaction.”  
> “Make this feel more tense.”

Clappy treats those as direction, not dialogue.

When the take ends, there is already a synchronized rough cut — while every original camera recording remains available.

Afterward, the filmmaker can redirect the same material:

> “Make Bella dominate this version.”  
> “Open wider.”  
> “Hold Tom longer before the reveal.”

Clappy creates another cut without destroying the first.

The goal is not to replace filmmaking judgment. It is to give tiny crews capabilities that normally require more people, more equipment, and much more post-production work.

---

## Why this should exist

Low-budget filmmakers can already shoot excellent footage on phones.

The hard part is everything around the cameras:

- coordinating several devices;
- starting and stopping them together;
- keeping their footage synchronized;
- tracking where the scene is in the script;
- deciding which camera should be live;
- turning several full recordings into an editable multicamera sequence;
- making alternate cuts without manually rebuilding the timeline.

Existing multicamera tools largely solve recording and synchronization. Existing AI editors largely operate after the footage already exists.

Clappy's bet is different:

> **What if the editing intelligence is present during the shoot?**

---

## The hackathon

Clappy is being built for **Agentic Cinema: The Blockbuster Hackathon**.

### Track

**ClickHouse**

The ClickHouse integration should be real, visible, and structurally useful — not sponsor decoration.

Clappy creates a continuous stream of production events:

- camera state;
- timestamps and synchronization;
- scene and take;
- script position;
- current speaker;
- camera assignments;
- live switching decisions;
- director instructions;
- shot history;
- alternate edit decisions;
- system events and confidence/state changes.

ClickHouse is the production memory behind the agent.

Gemini should be able to use ClickHouse through the required ClickHouse MCP integration to understand what has happened across the shoot and reason about what should happen next.

For example:

> “Which camera has Bella?”  
> “What have we shown during this exchange?”  
> “How long have we stayed on Tom?”  
> “What happened during Take 3?”  
> “Build another cut where Bella carries the scene.”

If removing ClickHouse leaves Clappy essentially unchanged, the integration is not deep enough.

### Required AI direction

The hackathon requires Google Cloud AI. The intended intelligence layer is therefore **Gemini / Google Cloud Agent tooling**, including Gemini Live where useful.

No non-Google AI model should be required in the submitted runtime unless the official rules clearly permit it.

---

## What should feel magical

The demo should not depend on explaining the architecture first.

A strong version should be understandable by watching it happen.

Several phones are physically present.

A scene is loaded.

The director says:

> “Clappy, roll.”

All cameras begin recording and confirm that they are synchronized.

Two actors perform.

Nobody is sitting behind a traditional video switcher.

The program feed changes cameras as the scene unfolds.

The director gives one live instruction and Clappy obeys it.

Then:

> “Clappy, cut.”

The take stops everywhere.

A multicamera timeline already exists.

The scene plays.

Then the director gives a creative note, and the same raw performance becomes a visibly different cut.

The product should leave the impression:

> **“That entire little film crew was being coordinated by the agent.”**

---

## Voice is part of the product, not decoration

Clappy should be operable without constantly touching screens.

Voice can control real production actions:

- load a scene;
- arm cameras;
- roll;
- cut;
- switch or hold a camera;
- modify the directing policy;
- replay a take;
- create an alternate cut.

Director communication should ideally travel through a dedicated control channel or headset rather than contaminate production audio.

If spoken direction does appear in camera audio, Clappy may use timing and reference signals to help isolate it, but the product should not rely on impossible promises of perfect speech removal when voices overlap.

---

## The camera philosophy

Each phone should remain a real camera, not just a remote webcam.

A strong architecture is:

- full-quality footage recorded locally;
- synchronized timestamps;
- lightweight state and preview information sent to the director;
- a live edit decision stream created centrally;
- full-resolution footage conformed to that decision history afterward.

The raw recordings are always preserved.

Clappy makes decisions about them. It does not destroy them.

---

## Current technical starting point

This is a starting hypothesis, **not a locked architecture**.

### Mobile
- React Native
- TypeScript
- VisionCamera
- native Swift modules only where they provide a clear advantage

### Director / product surface
- Next.js
- TypeScript

### Agent and backend
- Python
- FastAPI
- Google ADK / Gemini
- Gemini Live for conversational production control where appropriate

### Realtime coordination
- WebSockets
- WebRTC or lightweight preview/proxy transport where useful

### Production memory
- ClickHouse
- ClickHouse MCP

### Editing and media
- deterministic edit-decision representation
- FFmpeg
- OpenTimelineIO or another timeline representation if it materially helps

This stack is deliberately flexible.

**Codex should change any part of it when implementation evidence, platform constraints, hackathon requirements, or a clearly better architecture justify the change.**

Do not preserve a technology choice merely because it appears in this document.

The product behavior and demo matter more than the initial stack.

---

## Testing philosophy

The system should be testable without requiring several physical phones for every iteration.

Where practical, camera clients and production events should be simulatable so orchestration, synchronization, agent behavior, editing decisions, and failure cases can be exercised automatically.

Useful public test material includes:

### AMI Meeting Corpus
Real synchronized multicamera recordings with multiple speakers and transcripts.

Useful for:
- multicamera switching;
- synchronization;
- speaker-aware behavior;
- command compliance;
- repeatable evaluation.

### Tears of Steel source footage
Openly released production footage from the Blender Open Movie project.

Useful for:
- cinematic shot selection;
- script/scene reasoning;
- real film footage;
- alternate edit experiments;
- polished demonstration material where licensing and attribution are respected.

Synthetic fixtures can also generate deterministic camera feeds for CI.

For the final hackathon demo, however, Clappy should still visibly control multiple real devices at least once. The physical multicamera moment is part of what makes the product believable.

---

## What Clappy is not

Clappy is not:

- a generic chat assistant;
- a generic AI video editor;
- a screenplay generator;
- a TikTok auto-editor;
- a filter or effects app;
- a replacement for professional directors or editors;
- a system that deletes original footage;
- a ClickHouse demo with a filmmaking skin.

The core is **agentic coordination of a real multicamera shoot**.

---

## Product principles

### Preserve creative control

The filmmaker should always be able to override Clappy, inspect the raw cameras, and create another version.

### Make intelligence observable

When Clappy makes a meaningful choice, the system should be able to explain enough of the state behind it to make the behavior trustworthy without turning the experience into an engineering dashboard.

### Prefer deterministic execution

Gemini can reason about the scene and choose actions. Recording, synchronization, camera state, edit operations, and rendering should remain dependable software operations.

### Build for tiny crews first

The initial user is not a Hollywood studio.

Think:

- student filmmakers;
- indie directors;
- short-film teams;
- scripted YouTube creators;
- tiny production crews.

The product becomes compelling precisely because these users cannot afford the workflow Clappy approximates.

### Keep the raw material

The live cut is a head start, not a destructive final answer.

---

## Hackathon goal

The goal is not merely to submit a working project.

The goal is to build a **credible first version with a real path to winning the ClickHouse track**.

The project should score on all four judging dimensions:

**Technological Implementation**  
The multicamera orchestration, Google agent stack, ClickHouse runtime integration, synchronization, and deterministic editing pipeline should be substantive.

**Design**  
Clappy should feel like one coherent filmmaking product rather than a collection of demos.

**Potential Impact**  
The user and pain should remain specific: small crews gaining multicamera production capability without needing a dedicated switcher operator and heavy post-production workflow.

**Quality of the Idea**  
The non-obvious idea is not “AI edits video.” It is that **an agent can participate in the production process itself, using the screenplay, live performance, production state, and director intent to coordinate cameras and create the first cut while filming is happening.**

---

## Freedom to go beyond this document

This file defines the center of gravity, not the boundary.

Codex has permission to:

- improve the mechanism;
- simplify weak parts;
- replace technical choices;
- discover stronger interactions;
- add features that make the central idea more convincing;
- remove features that dilute it;
- find a better way to demonstrate the product;
- make the system more cinematic, surprising, or useful.

Do not turn the project into something unrelated simply for novelty, but do not treat this document as a specification that must be obeyed line by line.

Protect the core:

> **Clappy turns several ordinary phones into an AI-directed multicamera film crew.**

Everything else is open to improvement.
