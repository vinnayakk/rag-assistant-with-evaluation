# Merge your branch into the main branch

/

---

# Merge your branch into the main branch

After you have [created a branch](/topics/git/branch/), made the required changes, and [committed them locally](/topics/git/commit/),
you [push your branch](/topics/git/commit/#send-changes-to-gitlab) and its commits to GitLab.

In the response to the `git push`, GitLab provides a direct link to create the merge request. For example:

```
...
remote: To create a merge request for my-new-branch, visit:
remote:   https://gitlab.example.com/my-group/my-project/merge_requests/new?merge_request%5Bsource_branch%5D=my-new-branch
```

To get your branch merged into the main branch:

1. Go to the page provided in the link that was provided by Git and
   [create your merge request](/user/project/merge_requests/creating_merge_requests/). The merge request’s
   **Source branch** is your branch and the **Target branch** should be the main branch.
2. If necessary, have your [merge request reviewed](/user/project/merge_requests/reviews/#request-a-review).
3. Have someone [merge your merge request](/user/project/merge_requests/#merge-a-merge-request), or merge
   the merge request yourself, depending on your process.

## Related topics

* [Merge requests](/user/project/merge_requests/)
* [Merge methods](/user/project/merge_requests/methods/)
* [Merge conflicts](/user/project/merge_requests/conflicts/)
