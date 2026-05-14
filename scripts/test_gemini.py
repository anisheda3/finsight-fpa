import asyncio

from app.services.llm_service import generate_text_with_llm

async def main():
    text = await generate_text_with_llm(
        prompt="Say hello from Gemini in one sentence.",
        system_prompt="You are a concise assistant.",
    )
    print(text)

if __name__ == "__main__":
    asyncio.run(main())