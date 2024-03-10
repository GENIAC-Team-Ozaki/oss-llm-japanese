install:
	poetry install
	pre-commit install
	sh set_git_template.sh
