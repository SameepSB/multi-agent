from travel_comparator.api.main import create_app


def main() -> None:
    import uvicorn

    app = create_app()
    settings = app.state.settings
    uvicorn.run(app, host="0.0.0.0", port=settings.api_port)
