# Upgrade Docker instances

/

---

# Upgrade Docker instances

* Tier: Free, Premium, Ultimate
* Offering: GitLab Self-Managed

Upgrade a Docker-based instance to a later version of GitLab.

## Prerequisites

Before you upgrade a Docker instance, you must first
[read required information and perform required steps](/update/plan_your_upgrade/).

## Upgrade a Docker-based instance

To upgrade a Docker-based instance:

1. Consider [turning on maintenance mode](/administration/maintenance_mode/) during the upgrade.
2. Pause [running CI/CD pipelines and jobs](/update/plan_your_upgrade/#pause-cicd-pipelines-and-jobs).
3. [Upgrade GitLab Runner](https://docs.gitlab.com/runner/install/) to the same version as your target GitLab version.
4. Upgrade GitLab itself by either:
   * [Using Docker Engine](/update/docker/#upgrade-with-docker-engine).
   * [Using Docker Compose](/update/docker/#upgrade-with-docker-compose).

After you upgrade:

1. Unpause [running CI/CD pipelines and jobs](/update/plan_your_upgrade/#pause-cicd-pipelines-and-jobs).
2. If enabled, [turn off maintenance mode](/administration/maintenance_mode/#disable-maintenance-mode).
3. Run [upgrade health checks](/update/plan_your_upgrade/#run-upgrade-health-checks).

### Upgrade with Docker Engine

To upgrade a GitLab instance that was
[installed with Docker Engine](/install/docker/installation/#install-gitlab-by-using-docker-engine):

1. Create a [backup](/install/docker/backup/). As a minimum, back up
   [the database](/install/docker/backup/#create-a-database-backup) and the GitLab secrets file.
2. Stop the running container:

   shell

   ```
   sudo docker stop gitlab
   ```
3. Remove the existing container:

   shell

   ```
   sudo docker rm gitlab
   ```
4. Pull the new image:

   GitLab Enterprise Edition

   shell

   ```
   sudo docker pull gitlab/gitlab-ee:<version>-ee.0
   ```

   GitLab Community Edition

   shell

   ```
   sudo docker pull gitlab/gitlab-ce:<version>-ce.0
   ```
5. Ensure that the `GITLAB_HOME` environment variable is [defined](/install/docker/installation/#create-a-directory-for-the-volumes):

   shell

   ```
   echo $GITLAB_HOME
   ```
6. Create the container again with the
   [previously specified](/install/docker/installation/#install-gitlab-by-using-docker-engine) options:

   shell

   ```
   sudo docker run --detach \
   --hostname gitlab.example.com \
   --publish 443:443 --publish 80:80 --publish 22:22 \
   --name gitlab \
   --restart always \
   --volume $GITLAB_HOME/config:/etc/gitlab \
   --volume $GITLAB_HOME/logs:/var/log/gitlab \
   --volume $GITLAB_HOME/data:/var/opt/gitlab \
   --shm-size 256m \
   gitlab/gitlab-ee:<version>-ee.0
   ```

On the first run, GitLab reconfigures and upgrades itself.

### Upgrade with Docker Compose

To upgrade a GitLab instance that was
[installed with Docker Compose](/install/docker/installation/#install-gitlab-by-using-docker-compose):

1. Create a [backup](/install/docker/backup/). As a minimum, back up
   [the database](/install/docker/backup/#create-a-database-backup) and the GitLab secrets file.
2. Edit `docker-compose.yml` and change the version to pull.
3. Download the newest release and upgrade your GitLab instance:

   shell

   ```
   docker compose pull
   docker compose up -d
   ```
