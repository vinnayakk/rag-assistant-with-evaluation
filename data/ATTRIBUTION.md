# Attribution for `data/chroma_db/`

`data/chroma_db/` is the search index the hosted demo uses. It contains passages of the GitLab documentation, so this notice applies to it.

- **Work:** GitLab Documentation, a random sample of 147 English pages
- **Author:** © GitLab Inc.
- **Source:** https://docs.gitlab.com (downloaded 2026-10-05; see [SOURCE.md](../SOURCE.md) for how)
- **Licence:** [Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/)
- **Changes made:** the HTML pages were converted to Markdown, cleaned (page navigation, header and footer removed, images reduced to
  their alt text, relative links made absolute), split into chunks of about 450 tokens, and each chunk was turned into an embedding vector.
- **Licence of this adaptation:** CC BY-SA 4.0, the same as the original.

This project is not affiliated with or endorsed by GitLab Inc. The code in this repository is MIT licensed (see [LICENSE](../LICENSE)); that
licence does not cover this folder.
