# AI Gateway chart

/

---

# AI Gateway chart

* Tier: Premium, Ultimate
* Offering: GitLab Self-Managed
* Status: Experiment

The AI Gateway chart deploys the AI Gateway as a sub-chart alongside your GitLab instance.
It enables GitLab Duo Self-Hosted and the GitLab Duo Agent Platform on Kubernetes.
This feature is an [experiment](https://docs.gitlab.com/policy/development_stages_support/).

Prerequisites:

* TLS is required for the GitLab URL. In production mode, the AI gateway requires the GitLab endpoint to be secured to perform authentication with the GitLab instance.
  Because this configuration is set correctly by default, no action is required.
* Either:
  + A cloud license applied with [usage billing](https://docs.gitlab.com/subscriptions/gitlab_credits/) enabled.
  + An offline license with the
    [GitLab Duo Agent Platform Self-Hosted](https://docs.gitlab.com/subscriptions/subscription-add-ons/#gitlab-duo-agent-platform-self-hosted) addon.

## Configure and deploy the chart

To configure and deploy the chart:

1. Deploy the chart with the following configuration:

   yaml

   ```
   global:
     hosts:
       domain: <YOUR_DOMAIN>

   ai-gateway:
     install: true
   ```
2. Get the service hostname of the AI-Gateway with the following command:

   shell

   ```
   kubectl get svc -n <NAMESPACE> -l app.kubernetes.io/name=ai-gateway \
   -o jsonpath='{range .items[*]}{.metadata.name}.{.metadata.namespace}.svc{"\n"}{end}'
   ```
3. After the chart is deployed and your instance is available, on in the upper-right corner of your GitLab instance, select **Admin**.
4. In the left sidebar, select **GitLab Duo**.
5. Select **Change configuration** and:

   * Change the **Local AI Gateway URL** to `http://<SERVICE_HOST_NAME>`.
   * Change the **Local URL for the GitLab Duo Agent Platform service** to `<SERVICE_HOST_NAME>:50052`.
   * Clear the checkbox **Use TLS for the GitLab Duo Agent Platform service**.
   * If you are using an offline license, make sure you select a model for the **Code Suggestions** and the **GitLab Duo Agent Platform** features.
     For more information, see [configure GitLab to use self-hosted models](https://docs.gitlab.com/administration/gitlab_duo_self_hosted/configure_duo_features/).
6. Select **Save changes**.
7. On the **GitLab Duo** page (`/admin/gitlab_duo`), select **Run health check** to verify that everything is working correctly.

## Configure internal TLS

History

* [Introduced](https://gitlab.com/gitlab-org/distribution/team-tasks/-/work_items/1842) in GitLab 19.1.

Prerequisites:

* The `self-hosted-v19.1.X-ee` or later tag for the
  AI-Gateway [container image](https://gitlab.com/gitlab-org/modelops/applied-ml/code-suggestions/ai-assist/container_registry/3809284?orderBy=PUBLISHED_AT&search%5B%5D=self-hosted).
* A certificate for both possible service hostnames `<RELEASE_NAME>-ai-gateway` and `<RELEASE_NAME>-ai-gateway.<NAMESPACE>.svc`.

To configure TLS:

1. Add the issuing certificate to the secrets of your cluster with the following command:

   shell

   ```
   kubectl create secret tls aigw-tls --cert=<PATH-TO-CERT-FILE> --key=<PATH-TO-KEY-FILE> -n gitlab
   ```
2. Add the issuing certificate in the [Custom Certificate Authorities](/charts/charts/globals/#custom-certificate-authorities).
3. Deploy the chart with the following configuration:

   yaml

   ```
   global:
     hosts:
       domain: <YOUR_DOMAIN>
     # Custom authority configured before
     certificates:
       customCAs:
         - secret: secret-custom-ca

   ai-gateway:
     image:
       # A 19.1 or later tag is required
       tag: self-hosted-v19.1.0-ee
     install: true
     # Make sure the probes access the service under the right scheme
     livenessProbe:
       httpGet:
         scheme: HTTPS
     readinessProbe:
       httpGet:
         scheme: HTTPS
     # The name of the secret where the certificate and its keys are stored
     tls:
       secretName: aigw-tls
       caSecretName: secret-custom-ca # Same CA as above
   ```

Go to your GitLab Duo configuration page and change the following:

* Change the **Local AI Gateway URL** to `https://<SERVICE_HOST_NAME>`.
* Change the **Local URL for the GitLab Duo Agent Platform service** to `<SERVICE_HOST_NAME>:50052`.
* Enable the **Use TLS for the GitLab Duo Agent Platform service**.
* If you are using an offline license, make sure you select a model for the **Code Suggestions** and the **GitLab
  Duo Agent Platform** features. For more information, see [configure GitLab to use self-hosted models](https://docs.gitlab.com/administration/gitlab_duo_self_hosted/configure_duo_features/).

### TLS ciphers suites

History

* [Introduced](https://gitlab.com/gitlab-org/charts/gitlab/-/work_items/6542#note_3533842875) in GitLab 19.2.

Prerequisites:

* The `self-hosted-v19.2.X-ee` or later tag for the
  AI-Gateway [container image](https://gitlab.com/gitlab-org/modelops/applied-ml/code-suggestions/ai-assist/container_registry/3809284?orderBy=PUBLISHED_AT&search%5B%5D=self-hosted).

Currently the TLS cipher suite defaults to TLSv1.2. But it can be changed to any [OpenSSL cipher string](https://docs.openssl.org/3.0/man1/openssl-ciphers/)
by setting the `ai-gateway.tls.ssl_ciphers` like in the following example:

yaml

```
ai-gateway:
 image:
   tag: self-hosted-v19.2.0-ee
 install: true
 livenessProbe:
   httpGet:
     scheme: HTTPS
 readinessProbe:
   httpGet:
     scheme: HTTPS
 tls:
   secretName: aigw-tls
   caSecretName: secret-custom-ca
   # Here is where you configure your cipher string
   ssl_ciphers: ECDHE+AESGCM:DHE+AESGCM:ECDHE+CHACHA20:DHE+CHACHA20
```

Keep in mind that cipher suites below TLSv1.2 are not supported and will cause issues.

## Configure external access for GitLab Duo Workflow runners

History

* [Introduced](https://gitlab.com/gitlab-org/charts/gitlab/-/work_items/6542) in GitLab 19.2.

Prerequisites:

* The `self-hosted-v19.2.X-ee` or later tag for the
  AI-Gateway [container image](https://gitlab.com/gitlab-org/modelops/applied-ml/code-suggestions/ai-assist/container_registry/3809284?orderBy=PUBLISHED_AT&search%5B%5D=self-hosted).

GitLab Duo Workflow runners connect to the AI Gateway over gRPC from outside the cluster.
To expose the AI Gateway externally, set the parameter `global.gatewayApi.enabled` to `true`.

yaml

```
global:
  gatewayApi:
    enabled: true

ai-gateway:
  image:
    tag: self-hosted-v19.2.0-ee
```

Deploy the changes, then go to your GitLab Duo configuration page and change the following:

* Change the **Local AI Gateway URL** to `https://ai-gateway.<YOUR_DOMAIN>`.
* Change the **Local URL for the GitLab Duo Agent Platform service** to `grpc-ai-gateway.<YOUR_DOMAIN>:443`.
* Enable the **Use TLS for the GitLab Duo Agent Platform service**.
* If you are using an offline license, make sure you select a model for the **Code Suggestions** and the **GitLab
  Duo Agent Platform** features. For more information, see [configure GitLab to use self-hosted models](https://docs.gitlab.com/administration/gitlab_duo_self_hosted/configure_duo_features/).

### End to end encryption

To benefit from end to end encryption from the client all the way to the pod, make sure to enable [internal TLS](/charts/charts/ai-gateway/#configure-internal-tls).
This is the recommended configuration.

yaml

```
global:
  gatewayApi:
    enabled: true

ai-gateway:
  install: true
  image:
    tag: self-hosted-v19.2.0-ee
  livenessProbe:
    httpGet:
      scheme: HTTPS
  readinessProbe:
    httpGet:
      scheme: HTTPS
tls:
  secretName: aigw-tls
  caSecretName: secret-custom-ca
```
