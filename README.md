<div align="center">
  <img src="https://github.com/yinan-c/RSSbrew/assets/95043151/15876fda-28aa-468f-b012-f1bbc4c03a84" alt="RSSbrew Icon" width="180"/>
  <h1>RSSBrew</h1>
</div>

A self-hosted, easy-to-deploy RSS tool that allows you to aggregate multiple RSS feeds, apply custom filters, and generate AI summaries.

⚠️This project is still under development. The current version may contain bugs or incomplete features. Please report any issues you encounter. Suggestions and contributions are welcome. Documentation in progress.

## Features

### 1. Custom Filters
Apply custom filters to your feeds to control what content gets through or not. You can filter based on Link, Title and Description.
Besides:
- Various match types including contains, does not contain, matches regex or not.
- Multiple filters can be applied together with various relationship operators: AND, OR, NOT.
- You can set the filter scope to apply to filter out matched entries entirely or filter for summary generation only.
  
### 2. Aggregate Multiple Feeds
Easily combine multiple RSS feeds into a single processed feed, even more powerful when used with custom filters.

### 3. Article Summarization
Using AI (currently supports GPT-3.5 Turbo, GPT-4 Turbo or GPT-4o, more planned) to generate and prepend the following directly to the article. The default summaries include a one-line summary and a slightly longer summary. You can also customize your prompt to use AI for other purposes.
  
### 4. Digests with AI

If you are overwhelmed by the number of articles, you can set up digests aggregating articles into one entry on a daily or weekly basis.
You can optionally choose what to include in the digest (e.g. content, summary, ) and use AI to help you summarize the digest.

## INSTALL

Docker deployment or regular installation supported, please refer to [INSTALL.md](INSTALL.md).

## LICENSE

This project is licensed under the AGPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## SUPPORT

If you find this project helpful, please consider leaving a star or supporting the development by [buying me a coffee](https://www.buymeacoffee.com/yinan).
We would greatly appreciate your support to keep this project going.