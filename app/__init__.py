"""Plico quoting tool - Flask application factory."""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .quote_engine import PAYMENT_TYPES, SOLUTION_TYPES, QuoteError, build_quote

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "pricing.json"


def load_config(path: str | os.PathLike | None = None) -> dict:
    with open(path or os.environ.get("PLICO_PRICING_CONFIG", DEFAULT_CONFIG), encoding="utf-8") as fh:
        return json.load(fh)


def create_app(config_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["PRICING"] = load_config(config_path)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "config_version": app.config["PRICING"].get("version")}

    @app.get("/api/config")
    def config():
        cfg = app.config["PRICING"]
        return {
            "version": cfg.get("version"),
            "packages": cfg["packages"],
            "site_adders": {k: v["label"] for k, v in cfg["site_adders"].items()},
            "solution_types": SOLUTION_TYPES,
            "payment_types": sorted(PAYMENT_TYPES),
            "finance": cfg["finance"],
            "default_markup_pct": cfg["margin"]["default_markup_pct"],
            "savings_defaults": cfg["savings"],
        }

    @app.post("/api/quote")
    def quote():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Request body must be a JSON object"), 400
        try:
            return jsonify(build_quote(payload, app.config["PRICING"]))
        except QuoteError as exc:
            return jsonify(error=str(exc)), 422

    return app
