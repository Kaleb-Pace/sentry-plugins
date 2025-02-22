from __future__ import absolute_import

from rest_framework.response import Response

from sentry.plugins.bases.issue2 import IssuePlugin2, IssueGroupActionEndpoint
from sentry.utils.http import absolute_uri

from sentry_plugins.exceptions import ApiError

from .mixins import BitbucketMixin
from .repository_provider import BitbucketRepositoryProvider


ISSUE_TYPES = (
    ("bug", "Bug"),
    ("enhancement", "Enhancement"),
    ("proposal", "Proposal"),
    ("task", "Task"),
)

PRIORITIES = (
    ("trivial", "Trivial"),
    ("minor", "Minor"),
    ("major", "Major"),
    ("critical", "Critical"),
    ("blocker", "Blocker"),
)

ERR_404 = (
    "Bitbucket returned a 404. Please make sure that "
    "the repo exists, you have access to it, and it has "
    "issue tracking enabled."
)


class BitbucketPlugin(BitbucketMixin, IssuePlugin2):
    description = "Integrate Bitbucket issues by linking a repository to a project."
    slug = "bitbucket"
    conf_title = BitbucketMixin.title
    conf_key = "bitbucket"
    auth_provider = "bitbucket"

    def get_group_urls(self):
        return super(BitbucketPlugin, self).get_group_urls() + [
            (
                r"^autocomplete",
                IssueGroupActionEndpoint.as_view(view_method_name="view_autocomplete", plugin=self),
            )
        ]

    def get_url_module(self):
        return "sentry_plugins.bitbucket.urls"

    def is_configured(self, request, project, **kwargs):
        return bool(self.get_option("repo", project))

    def get_new_issue_fields(self, request, group, event, **kwargs):
        fields = super(BitbucketPlugin, self).get_new_issue_fields(request, group, event, **kwargs)
        return (
            [
                {
                    "name": "repo",
                    "label": "Bitbucket Repository",
                    "default": self.get_option("repo", group.project),
                    "type": "text",
                    "readonly": True,
                }
            ]
            + fields
            + [
                {
                    "name": "issue_type",
                    "label": "Issue type",
                    "default": ISSUE_TYPES[0][0],
                    "type": "select",
                    "choices": ISSUE_TYPES,
                },
                {
                    "name": "priority",
                    "label": "Priority",
                    "default": PRIORITIES[0][0],
                    "type": "select",
                    "choices": PRIORITIES,
                },
            ]
        )

    def get_link_existing_issue_fields(self, request, group, event, **kwargs):
        return [
            {
                "name": "issue_id",
                "label": "Issue",
                "default": "",
                "type": "select",
                "has_autocomplete": True,
            },
            {
                "name": "comment",
                "label": "Comment",
                "default": absolute_uri(
                    group.get_absolute_url(params={"referrer": "bitbucket_plugin"})
                ),
                "type": "textarea",
                "help": (
                    "Leave blank if you don't want to " "add a comment to the Bitbucket issue."
                ),
                "required": False,
            },
        ]

    def message_from_error(self, exc):
        if isinstance(exc, ApiError) and exc.code == 404:
            return ERR_404
        return super(BitbucketPlugin, self).message_from_error(exc)

    def create_issue(self, request, group, form_data, **kwargs):
        client = self.get_client(request.user)

        try:
            response = client.create_issue(
                repo=self.get_option("repo", group.project), data=form_data
            )
        except Exception as e:
            self.raise_error(e, identity=client.auth)

        return response["local_id"]

    def link_issue(self, request, group, form_data, **kwargs):
        client = self.get_client(request.user)
        repo = self.get_option("repo", group.project)
        try:
            issue = client.get_issue(repo=repo, issue_id=form_data["issue_id"])
        except Exception as e:
            self.raise_error(e, identity=client.auth)

        comment = form_data.get("comment")
        if comment:
            try:
                client.create_comment(repo, issue["local_id"], {"content": comment})
            except Exception as e:
                self.raise_error(e, identity=client.auth)

        return {"title": issue["title"]}

    def get_issue_label(self, group, issue_id, **kwargs):
        return "Bitbucket-%s" % issue_id

    def get_issue_url(self, group, issue_id, **kwargs):
        repo = self.get_option("repo", group.project)
        return "https://bitbucket.org/%s/issue/%s/" % (repo, issue_id)

    def view_autocomplete(self, request, group, **kwargs):
        field = request.GET.get("autocomplete_field")
        query = request.GET.get("autocomplete_query")
        if field != "issue_id" or not query:
            return Response({"issue_id": []})

        repo = self.get_option("repo", group.project)
        client = self.get_client(request.user)

        try:
            response = client.search_issues(repo, query.encode("utf-8"))
        except Exception as e:
            return Response(
                {"error_type": "validation", "errors": [{"__all__": self.message_from_error(e)}]},
                status=400,
            )

        issues = [
            {"text": "(#%s) %s" % (i["local_id"], i["title"]), "id": i["local_id"]}
            for i in response.get("issues", [])
        ]

        return Response({field: issues})

    def get_configure_plugin_fields(self, request, project, **kwargs):
        return [
            {
                "name": "repo",
                "label": "Repository Name",
                "type": "text",
                "placeholder": "e.g. getsentry/sentry",
                "help": "Enter your repository name, including the owner.",
                "required": True,
            }
        ]

    def setup(self, bindings):
        bindings.add("repository.provider", BitbucketRepositoryProvider, id="bitbucket")
