---
template_id: builder
base_name: builder
default_target_puller: puller-01
default_model: qwen3.5:27b
---
# Builder template

Spawn software-builder instances from this definition.

Control-plane harness sessions that should be picked up by a running
builder worker must target puller `builder-01` (or send
`definition: builder` once the control-plane supports that field).
The instance itself still sends LLM turns to `puller-01`.
