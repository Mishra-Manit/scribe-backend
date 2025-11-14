# Contains the PipelineRunner class, BasePipelineStep class, StepResult class, 


from dataclasses import dataclass


@dataclass
class StepResult:

    success: bool
    # Fill rest out


class BasePipelineStep(ABC):
    # Base case for all pipeline steps

    def __init__(self, step_name: str):
        self.step_name = step_name
        self.logger = logging.getLogger(f"pipeline.{step_name}")
        self._global_state: Optional[PipelineGlobalState] = None

    async def execute(self, pipeline_data: PipelineData) -> StepResult:
        # Execute the pipeline step with error handling and timing
        # takes current pipeline data as arg
        # returns stepresult with execution details