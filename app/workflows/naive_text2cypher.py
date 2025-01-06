import asyncio

from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)

from app.workflows.frontend_events import StringEvent
from app.workflows.naive_text2cypher_steps import (
    generate_cypher_step,
    naive_final_answer_prompt,
)
from app.workflows.utils import graph_store, llm


class SummarizeEvent(Event):
    question: str
    cypher: str
    context: str


class ExecuteCypherEvent(Event):
    question: str
    cypher: str


class NaiveText2CypherFlow(Workflow):
    @step
    async def generate_cypher(self, ctx: Context, ev: StartEvent) -> ExecuteCypherEvent:
        question = ev.input

        cypher_query = await generate_cypher_step(question)

        ctx.write_event_to_stream(
            StringEvent(
                result=f"Generated Cypher: {cypher_query}", label="Cypher generation"
            )
        )

        # Return for the next step
        return ExecuteCypherEvent(question=question, cypher=cypher_query)

    @step
    async def execute_query(
        self, ctx: Context, ev: ExecuteCypherEvent
    ) -> SummarizeEvent:
        try:
            database_output = str(graph_store.structured_query(ev.cypher))
        except Exception as e:
            database_output = str(e)
        return SummarizeEvent(
            question=ev.question, cypher=ev.cypher, context=database_output
        )

    @step
    async def summarize_answer(self, ctx: Context, ev: SummarizeEvent) -> StopEvent:
        gen = await llm.astream_chat(
            naive_final_answer_prompt.format_messages(
                context=ev.context, question=ev.question, cypher_query=ev.cypher
            )
        )
        final_event = StringEvent(result="", label="Final answer")
        async for response in gen:
            final_event.result = response.delta
            ctx.write_event_to_stream(final_event)
            await asyncio.sleep(0.05)

        stop_event = StopEvent(result="Workflow completed.")

        # Return the final result
        return stop_event
