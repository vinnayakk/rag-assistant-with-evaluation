# Features inside the.gitlab/directory

/

---

# Features inside the `.gitlab/` directory

We have implemented standard features that depend on configuration files in the `.gitlab/` directory. You can find `.gitlab/` in various GitLab repositories.
When implementing new features, refer to these existing features to avoid conflicts:

* [Description templates](/user/project/description_templates/#create-a-description-template): `.gitlab/issue_templates/`.
* [Merge request templates](/user/project/description_templates/#create-a-merge-request-template): `.gitlab/merge_request_templates/`.
* [GitLab agent for Kubernetes](https://gitlab.com/gitlab-org/cluster-integration/gitlab-agent): `.gitlab/agents/`.
* [CODEOWNERS](/user/project/codeowners/#set-up-code-owners): `.gitlab/CODEOWNERS`.
* [Route Maps](/ci/review_apps/#route-maps): `.gitlab/route-map.yml`.
* [Customize Auto DevOps Helm Values](/topics/autodevops/customize/#customize-helm-chart-values): `.gitlab/auto-deploy-values.yaml`.
* [Insights](/user/project/insights/#for-projects): `.gitlab/insights.yml`.
* [Service Desk templates](/user/project/service_desk/configure/#customize-emails-sent-to-external-participants): `.gitlab/service_desk_templates/`.
* [Secret detection custom rulesets](/user/application_security/secret_detection/pipeline/configure/#customize-analyzer-rulesets): `.gitlab/secret-detection-ruleset.toml`
* [Static analysis custom rulesets](/user/application_security/sast/customize_rulesets/): `.gitlab/sast-ruleset.toml`
