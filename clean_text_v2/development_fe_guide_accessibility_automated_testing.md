# Automated accessibility testing

/

---

# Automated accessibility testing

GitLab is committed to ensuring our platform is accessible to all users. We use automated accessibility testing as part of our comprehensive approach to identify and prevent accessibility barriers.

[We aim to conform to level AA of the World Wide Web Consortium (W3C) Web Content Accessibility Guidelines 2.1](https://design.gitlab.com/accessibility/a11y).

## Our testing approach

GitLab uses multiple approaches for automated accessibility testing to provide comprehensive coverage:

1. **[Feature tests](/development/fe_guide/accessibility/feature_tests/)** - End-to-end accessibility testing using axe-core in feature tests to validate complete user flows and page interactions
2. **[Storybook component tests](/development/fe_guide/accessibility/storybook_tests/)** - Isolated component testing using Storybook test-runner with axe-playwright to ensure individual Vue components meet accessibility standards

These complementary approaches ensure that both individual components and complete user experiences are accessible.
