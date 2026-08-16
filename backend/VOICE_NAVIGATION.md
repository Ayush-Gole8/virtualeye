# Voice Navigation

## Request flow

1. `VoiceNavigationContext.jsx` recognizes a natural scene question and dispatches the complete utterance.
2. `VisionPage.jsx` pauses recognition and periodic narration, captures one current frame, and sends the frame, question, and stable browser `session_id` to `/question`.
3. `engine/dialogue.py` classifies the intent and resolves references from short-lived session context.
4. `server.py` runs YOLO and metric depth once, using Florence-2 only when open-vocabulary or dense-region reasoning is needed.
5. `engine/narrate.py` returns one concise spoken response. Requested answers are spoken in both Priority and Naive modes.

## Supported conversations

- `Find my remote.`
- `Where can I find my glasses?`
- `Can you see my bottle?`
- `Check again.` or `Can you see it now?`
- `How far is it?`
- `Which side is my bottle?`
- `Can I reach it?`
- `Anything else on this table?`
- `What's on it?`
- `What is next to it?`
- `What do you see?`

The session remembers the most recently requested object and inferred support surface for 15 minutes. Camera restart resets that browser session.

## Response policy

- Lead with confirmation or uncertainty: `I found your bottle` or `I can see what appears to be your remote`.
- Give a camera-relative location before an action: left, right, straight ahead, above hand level, or below hand level.
- Use direct reach instructions only when metric depth places the target within the configured reach threshold.
- If distance is missing or the target is farther away, ask the user to move closer and check again before reaching.
- If the target is absent, ask the user to pan the camera slowly from left to right instead of repeating a generic failure message.
- Surface and nearby-object relations are phrased cautiously because they are inferred from two-dimensional bounding-box geometry.

## Safety limits

- Left/right guidance assumes the camera points in the same direction as the user. The front-camera capture is mirrored to match the user-facing preview; the rear camera is preferred for mobile navigation.
- Reach guidance is advisory, not collision-free path planning. Unknown depth never produces an immediate reach command.
- Florence open-vocabulary matches are marked as tentative in speech.
- Priority mode continues to suppress unsolicited non-hazards. A direct user question still receives a spoken answer.
- The browser pauses new voice recognition during a scene request and keeps periodic narration muted long enough for the answer to finish.

## Validation

Run the lightweight checks without loading the models:

```powershell
cd backend
.\.venv\Scripts\python.exe -m py_compile .\engine\dialogue.py .\engine\vlm.py .\engine\narrate.py .\server.py
```

Build the frontend:

```powershell
npm.cmd run build
```

A real camera/GPU test is still required to tune the reach threshold and validate table-support geometry for the intended camera mounting position.
