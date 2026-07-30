#!/bin/sh
set -e

REPO_URL=https://github.com/ait-detectmate/DetectMateLibrary.git

if [ $# -eq 0 ]
then
	echo "No branch selected. Keeping original pyproject.toml"
	exit 0
fi

if [ "$1" != "main" ]
then
	BRANCH="development"
else
	BRANCH="main"
fi

echo "Using branch: $BRANCH"

# Resolve to a commit SHA instead of pinning the git dependency to the
# branch name. This gives CI caching (uv's own cache and the workflow's
# actions/cache step) a stable key to work with: reruns against the same
# library commit hit cache instead of re-cloning/re-resolving every time.
SHA=$(git ls-remote "$REPO_URL" "refs/heads/${BRANCH}" | cut -f1)

if [ -z "$SHA" ]
then
	echo "Could not resolve branch '${BRANCH}' on ${REPO_URL}" >&2
	exit 1
fi

echo "Resolved ${BRANCH} to ${SHA}"

GIT_SOURCE="git+${REPO_URL}@${SHA}"
sed -i -E "s|detectmatelibrary==[^\"]+|detectmatelibrary @ ${GIT_SOURCE}|g" pyproject.toml

if [ -n "$GITHUB_OUTPUT" ]
then
	echo "library_sha=${SHA}" >> "$GITHUB_OUTPUT"
fi
