SENTRY_PATH := `python -c 'import sentry; print sentry.__file__.rsplit("/", 3)[0]'`
UNAME_S := $(shell uname -s)

PIP_VERSION := 19.1.1
PIP_OPTS := --no-use-pep517 --disable-pip-version-check

develop: ensure-pip setup-git install-yarn
	pip install -e git+https://github.com/getsentry/sentry.git#egg=sentry[dev,optional] $(PIP_OPTS)
	pip install -e ".[tests]" $(PIP_OPTS)
	yarn install

ensure-pip:
	pip install "pip==$(PIP_VERSION)"

install-yarn:
	@echo "--> Installing Node dependencies"
	@hash yarn 2> /dev/null || npm install -g yarn
	# Use NODE_ENV=development so that yarn installs both dependencies + devDependencies
	NODE_ENV=development yarn install --ignore-optional

install-tests: develop
	pip install ".[tests]" $(PIP_OPTS)

setup-git:
	@echo "--> Installing git hooks"
	git config branch.autosetuprebase always
	git config core.ignorecase false
	cd .git/hooks && ln -sf ../../config/hooks/* ./
	pip install "pre-commit>=1.10.1,<1.11.0" $(PIP_OPTS)
	pre-commit install --install-hooks
	@echo ""

clean:
	@echo "--> Cleaning static cache"
	rm -f src/sentry_plugins/*/static/dist
	@echo "--> Cleaning pyc files"
	find . -name "*.pyc" -delete
	@echo "--> Cleaning python build artifacts"
	rm -rf build/ dist/ src/sentry_plugins/assets.json
	@echo ""

lint: lint-js lint-python

lint-python:
	@echo "--> Linting python"
	bash -eo pipefail -c "flake8 | tee .artifacts/flake8.pycodestyle.log"
	@echo ""

lint-js:
	@echo "--> Linting javascript"
	bash -eo pipefail -c "${SENTRY_PATH}/bin/lint --js --parseable . | tee .artifacts/eslint.codestyle.xml"
	@echo ""

test: install-tests
	py.test

.PHONY: develop install-tests
