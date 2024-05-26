<div align="center">
  <img src="https://github.com/yinan-c/RSSbrew/assets/95043151/15876fda-28aa-468f-b012-f1bbc4c03a84" alt="RSSbrew Icon" width="180"/>
  <h1>RSSBrew</h1>
</div>

A self-hosted, easy-to-deploy RSS tool that allows you to aggregate multiple RSS feeds, apply custom filters, and generate AI summaries.

⚠️This project is still under development. The current version may contain bugs or incomplete features. Please use it with caution and report any issues you encounter.

## Features

### 1. Custom Filters
Apply custom filters to your feeds to control what content gets through or not. You can filter based on Link, Title and Description.
Besides:
- Various match types including contains, does not contain, matches regex or not.
- Multiple filters can be applied together with various relationship operators: AND, OR, NOT.
- You can set the filter scope to apply to filter out matched entries entirely or filter for summary generation only.
  
### 2. Aggregate Multiple RSS Feeds
Easily combine multiple RSS feeds into a single processed feed, even more powerful when used with custom filters.

### 3. AI Summarization
Leverage AI power (currently supports GPT-3.5 Turbo, GPT-4 Turbo or GPT-4o, more planned) to generate and append the following directly to the article.

- 5 keywords
- Summary in custom language
  
## 4. Custom Prompt
Optional custom prompt if you wish to use AI for other purposes.

### 4. Auth code for RSS feed
You can set an auth code for the feeds, only users with the correct auth code can access the feed.

## INSTALL

Please refer to [INSTALL.md](INSTALL.md).

## LICENSE

This project is licensed under the AGPL-3.0 License - see the [LICENSE](LICENSE) file for details.
