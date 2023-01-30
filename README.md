# README

## DEPLOY

```bash
python -m unittest
bumpversion patch --commit
python setup.py sdist
twine upload --skip-existing dist/*
```
