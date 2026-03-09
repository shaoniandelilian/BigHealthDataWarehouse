import logging
from core.context import Context
from core.pipeline import Pipeline
import yaml

# Load pipeline config
with open("configs/pipeline_legacy_enhanced.yaml") as f:
    cfg = yaml.safe_load(f)

# Initialize engine
engine = Pipeline(cfg["pipeline_steps"], pipeline_name="legacy_enhanced")

# Create a mock pending context that looks like it just passed review
# It needs 'chunks' in metadata so the embedder and loader have something to process
ctx = Context(raw_data={"file_path": "/test/path.pdf"})
ctx.metadata["chunks"] = [{"text": "This is a test chunk to be embedded and loaded."}]
ctx.paused_at_step = 4 # Index of YuanEmbedderProcessor
ctx.is_pending_review = False # We approved it
ctx.is_valid = True

class TraceProcessor:
    def __init__(self, name): self.name = name
    def process(self, context): return context

for p in engine.processors:
    original_process = p.process
    def make_wrapper(orig, name):
        def wrapper(context):
            print(f"Starting {name}...")
            ctx = orig(context)
            print(f"Finished {name}. Valid={ctx.is_valid}")
            if not ctx.is_valid:
                print(f"Errors so far: {ctx.errors}")
            return ctx
        return wrapper
    p.process = make_wrapper(original_process, p.__class__.__name__)

print("Resuming pipeline from step 4 (YuanEmbedder)...")
final_ctx = engine.run(ctx, start_index=ctx.paused_at_step)
print("Pipeline run completed!")
print(f"Final status: Valid={final_ctx.is_valid}")
print(f"Errors: {final_ctx.errors}")
