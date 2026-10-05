# Tutorial: Scan a Docker container for vulnerabilities

/

---

# Tutorial: Scan a Docker container for vulnerabilities

* Tier: Free, Premium, Ultimate
* Offering: GitLab.com, GitLab Self-Managed, GitLab Dedicated

You can use [container scanning](/user/application_security/container_scanning/) to check for vulnerabilities
in container images stored in the [container registry](/user/packages/container_registry/).

Container scanning configuration is added to the pipeline configuration of a project. In this tutorial, you:

1. Create a [new project](/tutorials/container_scanning/#create-a-new-project).
2. [Add a `Dockerfile`](/tutorials/container_scanning/#add-a-dockerfile-to-new-project) file to the project. This `Dockerfile` contains minimal
   configuration required to create a Docker image.
3. Create [pipeline configuration](/tutorials/container_scanning/#create-pipeline-configuration) for the new project to create a Docker
   image from the `Dockerfile`, build and push a Docker image to the container registry, and then scan the Docker image
   for vulnerabilities.
4. Check for [reported vulnerabilities](/tutorials/container_scanning/#check-for-reported-vulnerabilities).
5. [Update the Docker image](/tutorials/container_scanning/#update-the-docker-image) and scan the updated image.

## Create a new project

To create the new project

1. In the upper-right corner, select **Create new** ( ) and **New project/repository**.
2. Select **Create blank project**.
3. In **Project name**, enter `Tutorial container scanning project`.
4. In **Project URL**, select a namespace for the project.
5. Select **Create project**.

## Add a `Dockerfile` to new project

To provide something for container scanning to work on, create a `Dockerfile` with very minimal configuration:

1. In your `Tutorial container scanning project` project, select  > **New file**.
2. Enter the filename `Dockerfile`, and provide the following contents for the file:

   dockerfile

   ```
   FROM hello-world:latest
   ```

Docker images created from this `Dockerfile` are based on [`hello-world`](https://hub.docker.com/_/hello-world) Docker
image.

1. Select **Commit changes**.

## Create pipeline configuration

Now you’re ready to create pipeline configuration. The pipeline configuration:

1. Builds a Docker image from the `Dockerfile` file, and pushes the Docker image to the container registry. The
   `build-image` job uses [Docker-in-Docker](/ci/docker/using_docker_build/) as a
   [CI/CD service](/ci/services/) to build the Docker image.
2. Includes the `Container-Scanning.gitlab-ci.yml` template, to scan the Docker image stored in the container registry.

To create the pipeline configuration:

1. In the root directory of your project, select  > **New file**.
2. Enter the filename `.gitlab-ci.yml`, and provide the following contents for the file:

   yaml

   ```
   include:
     - template: Jobs/Container-Scanning.gitlab-ci.yml

   container_scanning:
     variables:
       CS_IMAGE: $CI_REGISTRY_IMAGE/tutorial-image

   build-image:
     image: docker:24.0.2-cli
     stage: build
     services:
       - docker:24.0.2-dind
     script:
       - docker build --tag $CI_REGISTRY_IMAGE/tutorial-image --file Dockerfile .
       - docker login --username gitlab-ci-token --password $CI_JOB_TOKEN $CI_REGISTRY
       - docker push $CI_REGISTRY_IMAGE/tutorial-image
   ```
3. Select **Commit changes**.

You’re almost done. After you commit the file, a new pipeline starts with this configuration.
When it’s finished, you can check the results of the scan.

## Check for reported vulnerabilities

Vulnerabilities for a scan are located on the pipeline that ran the scan. To check for reported vulnerabilities:

1. Select **CI/CD** > **Pipelines** and select the most recent pipeline. This pipeline should consist of a job called
   `container_scanning` in the `test` stage.
2. If the `container_scanning` job was successful, select the **Security** tab. If any vulnerabilities were found, they
   are listed on that page.

## Update the Docker image

A Docker image based on `hello-world:latest` is unlikely to show any vulnerabilities. For an example of a scan that
reports vulnerabilities:

1. In the root directory of your project, select the existing `Dockerfile` file.
2. Select **Edit**.
3. Replace `FROM hello-world:latest` with a different Docker image for the
   [`FROM`](https://docs.docker.com/reference/dockerfile/#from) instruction. The best Docker images to demonstrate
   container scanning have:
   * Operating system packages. For example, from Debian, Ubuntu, Alpine, or Red Hat.
   * Programming language packages. For example, NPM packages or Python packages.
4. Select **Commit changes**.

After you commit changes to the file, a new pipeline starts with this updated `Dockerfile`. When it’s finished, you can
check the results of the new scan.
