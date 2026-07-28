# Publishing to PyPI

The package is built, tested and on GitHub. Publishing needs a PyPI account, which is yours
to create — it's tied to your identity as the author.

## One-time setup (~5 min)

1. Create an account: https://pypi.org/account/register/ (verify the email)
2. Enable 2FA when prompted — PyPI requires it for publishing.
3. Create an API token: https://pypi.org/manage/account/token/
   - Scope: **"Entire account"** for the first upload (you can narrow it to the
     `tradevodata` project afterwards).
   - Copy the token — it's shown once and starts with `pypi-`.

## Publish

From `~/tradevodata-py`:

```bash
python3 -m twine upload dist/*
```

- Username: `__token__`
- Password: paste the `pypi-...` token

Takes about 10 seconds. Then `pip install tradevodata` works for anyone, anywhere.

## Test it worked

```bash
python3 -m venv /tmp/t && /tmp/t/bin/pip install tradevodata
/tmp/t/bin/python -c "import tradevodata as tv; print(len(tv.sample(to_pandas=False)), 'rows')"
```

## Releasing a new version later

1. Bump `version` in `pyproject.toml` **and** `__version__` in `src/tradevodata/__init__.py`
   (keep them identical).
2. `rm -rf dist/ && python3 -m build && python3 -m twine check dist/*`
3. `python3 -m twine upload dist/*`

PyPI will not let you overwrite a version that already exists, so every upload needs a new
number.

## After the first publish

Tell me and I'll add the install line to the site docs and README. Until it's actually live I
am deliberately not advertising `pip install tradevodata` anywhere — claiming an install
command that 404s is exactly the kind of thing this brand can't afford.
