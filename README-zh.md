# RSSBrew

<div align="center">
  <img src="https://github.com/user-attachments/assets/f3c46cec-bd6d-4184-9970-db3cb79a3c9e" alt="RSSbrew Icon" width="180"/>
  <h1>RSSBrew</h1>
</div>

[English](README.md) | 中文

RSSBrew 是一个自托管、易于部署的 RSS 工具，允许你聚合多个 RSS 源，应用自定义过滤器，生成 AI 文章摘要和每日/每周摘要。

Telegram 讨论群：[RSSBrew](https://t.me/rssbrew)

⚠️ 此项目仍在开发中。当前版本可能包含错误或未完成的功能。请在 issues 或者 telegram 群里报告遇到的任何问题。欢迎提供建议和贡献。完整文档正在进行中，请暂时参考[我博客中的介绍](https://yinan.me/rssbrew-config)。

### 示例订阅源

https://public.rssbrew.com/feeds/HN%20comments/

## 演示

https://demo.rssbrew.com

username: `admin`

password: `changeme` (数据每周会重置，请不要保存重要数据和使用后修改密码)

## 特性

### 1. 自定义过滤器

将自定义过滤器应用于你的订阅源，以控制哪些内容通过或不通过。你可以根据链接、标题和描述进行过滤。

此外：

- 支持多种匹配类型，包括包含、不包含、匹配正则表达式。
- 多个过滤器可以与关系运算符（AND、OR、NOT）一起分组，组之间的关系也可以设置。
- 你可以设置过滤器范围，以完全过滤匹配的条目，或仅用于摘要生成。

### 2. 聚合多个订阅源

将多个 RSS 源组合成一个处理后的订阅源，与自定义过滤器结合使用时更加强大。

### 3. 文章总结

使用 AI（目前支持所有 OpenAI 兼容的模型）生成总结并将其添加到文章前面。默认总结包括单行总结和全文总结。你还可以自定义提示以将 AI 用于其他目的。

### 4. AI 生成摘要

如果你的未读被大量文章所淹没，你可以设置摘要，将文章按日或按周聚合到一个条目中。

你可以选择在摘要中包含的内容（例如所有文章的目录、原文、文章总结等），并可以配置 AI 帮你进一步处理每日、每周摘要（比如归类、进一步筛选、按照重要性排序、变换格式、翻译内容等）。

## 安装

Docker 部署，请参阅 [INSTALL.md](INSTALL.md)。

## 许可证

本项目采用 AGPL-3.0 许可证 - 有关详细信息，请参阅 [LICENSE](LICENSE) 文件。

## 支持

感谢 [NodeSupport](https://github.com/NodeSeekDev/NodeSupport) 赞助了本项目的 demo 和公共示例的部署。

<div align="left">
  <a href="https://yxvm.com/">
    <img src="https://github.com/user-attachments/assets/ea85cf8c-9c83-4e57-a211-eb7708847647" width="300" />
  </a>
</div>

如果你发现此项目有帮助，请考虑 star 这个项目或通过捐赠来支持开发。非常感谢你的支持!


<a href='https://ko-fi.com/yinanc' target='_blank'> <img height='36'
style='border:0px;height:36px;' src='https://cdn.ko-fi.com/cdn/kofi1.png?v=3'
border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>
