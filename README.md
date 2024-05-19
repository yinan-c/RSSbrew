# RSSBrew

Self-hosted, easy-to-deploy RSS tool that allows you to aggregate multiple RSS feeds, apply custom filters, and generate AI-driven summaries.

## Disclaimer

This project is still under development. The current version is may contain bugs or incomplete features. Please use it with caution and report any issues you encounter.

## Features

### 1. Custom Filters
Apply custom filters to your feeds to control what content gets through or not. You can filter based on Link, Title and Description.
Besides:
- Various match types including contains, does not contain, matches regex or not.
- Multiple filtered can be applied together with various relationship operators: AND, OR, NOT.
- You can set filter scope to apply to filter out matched entries entirely or filter for summary generation only.
  
### 2. Aggregate Multiple RSS Feeds
Easily combine multiple RSS feeds into a single processed feed, even more powerful when used with custom filters.

### 3. AI Summarization
Leverage AI power(currently support GPT-3.5, GPT-4 Turbo and GPT-4o) to generate and append
directly to the article.

The summarization features include:
- Keyword extraction
- Summary generation in multiple languages

### 4. Auth code for RSS feed
You can set an auth code for the RSS feed, so that only users with the correct auth code can access the feed.

## Getting Started

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yinan-c/rssbrew.git
   cd rssbrew
   ```

2. **Build and Run the Docker Container**
   ```bash
   docker compose build
   docker compose up -d
   ```

3. **Access the Application**
   Open your browser and go to `http://localhost:8000/admin` to access the management interface. Configure your RSS feeds, filters, and settings from there.

## Configuration

- **Environment Variables**: Set environment variables such as `OPENAI_API_KEY`, `SECRET_KEY`.

## LICENSE

This project is licensed under the AGPL-3.0 License - see the [LICENSE](LICENSE) file for details.