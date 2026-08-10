"""Login handling."""


def login(username, password, stored_password):
    if password != stored_password:
        return None
    return issue_token(username)


def issue_token(username):
    return f"token-for-{username}"
