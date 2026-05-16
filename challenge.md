# Agentic Search Challenge

Build a system that takes a topic query (e.g., "AI startups in healthcare", "top pizza places in Brooklyn", "open source database tools") and produces a structured table of discovered entities with relevant attributes, sourced from the web.

## Minimum Requirements

- Accept a topic query
- Search the web for relevant results (use any search API, Brave, SerpAPI, etc.)
- Scrape and process web pages from search results
- Use LLMs to extract structured entity data from the scraped content
- Return a table of results in a structured format (JSON or rendered)
- Each cell value should be traceable to its source

## Guidelines

- Your solution can include a web API, a frontend, or both, up to you
- Any language or framework is fine
- Use any LLM API (OpenRouter, OpenAI, local models, etc.)
- You can use any AI coding tools for development

## How we'll evaluate

Your submission will be compared against other candidates on:

- **Output quality**: do the results actually make sense? Are they accurate and useful for real queries? Are latency and cost reasonable for a real system?
- **Design choices**: what problems did you identify and how did you solve them? What trade-offs did you make?
- **Code structure**: is the codebase well-organized and readable?
- **Documentation**: clear setup instructions, explanation of your approach, and known limitations
- **Complexity of implementation**: how far did you push the solution beyond the basics?

## Submission

Include a README with documentation, including description of your approach, the design decisions you made, any known limitations and setup instructions. Including a url with a live demo on a free tier cloud instance is also encouraged. Please share your code via a public GitHub repository by sending an email to csamarinas@umass.edu with this as your exact subject line 'CIIR challenge submission'.

**Deadline: Saturday, April 4th at 11:59 PM EDT.**

Good luck!
