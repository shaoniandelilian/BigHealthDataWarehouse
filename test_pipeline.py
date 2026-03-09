import logging
from core.context import Context
from core.pipeline import Pipeline
import yaml

with open("configs/pipeline_legacy_enhanced.yaml") as f:
    cfg = yaml.safe_load(f)

engine = Pipeline(cfg["pipeline_steps"], pipeline_name="legacy_enhanced")
ctx = Context(raw_data={"file_path": "/home/wuteng/realtime_rag_pipeline/data/pdf/718_智能体Fail_Aware_Agents_Structur-吴基.pdf"})

class TraceProcessor:
    def __init__(self, name): self.name = name
    def process(self, context):
        print(f"-> Executing: {self.name}, valid={context.is_valid}")
        return context

for i, p in enumerate(engine.processors):
    print(f"Loaded processor: {p.__class__.__name__}")
    # Wrap to see if it executes
    original_process = p.process
    def make_wrapper(orig, name):
        def wrapper(context):
            print(f"Starting {name}...")
            ctx = orig(context)
            print(f"Finished {name}. Valid={ctx.is_valid}, PendingReview={ctx.is_pending_review}")
            if not ctx.is_valid:
                print(f"Errors so far: {ctx.errors}")
            return ctx
        return wrapper
    p.process = make_wrapper(original_process, p.__class__.__name__)

print("Running pipeline...")
final_ctx = engine.run(ctx)
print("Pipeline run completed!")
print(f"Final status: Valid={final_ctx.is_valid}, PendingReview={final_ctx.is_pending_review}")
