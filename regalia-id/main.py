import base64
import os

import anthropic
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
client = anthropic.Anthropic()

ALLOWED_MIME = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}

SYSTEM_PROMPT = """You identify universities from academic regalia (graduation robes, hoods, gowns, tams, stoles).

Examine:
- Hood lining colors and pattern (chevrons, bars) — these often encode the school
- Gown color, trim, velvet panel color (velvet color indicates field of study, not school)
- Tassel/cord colors
- Any visible insignia, crests, or logos
- Hood shape and length (bachelor's/master's/doctoral)

Respond in JSON with this exact shape:
{
  "university": "Most likely university name, or null if you can't tell",
  "confidence": "low" | "medium" | "high",
  "degree_level": "bachelor's | master's | doctoral | unknown",
  "field_indicated": "Field of study the velvet color suggests, or null",
  "reasoning": "Brief explanation of what in the image led to this identification",
  "alternatives": ["Other universities this could plausibly be"]
}

If the image doesn't show regalia, set university to null and explain in reasoning."""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/identify", methods=["POST"])
def identify():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    mime = file.mimetype.lower() if file.mimetype else ""
    media_type = ALLOWED_MIME.get(mime)
    if not media_type:
        return jsonify({"error": f"Unsupported image type: {mime}"}), 400

    image_bytes = file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        return jsonify({"error": "Image too large (max 10MB)"}), 400

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "university": {"type": ["string", "null"]},
                        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                        "degree_level": {"type": "string"},
                        "field_indicated": {"type": ["string", "null"]},
                        "reasoning": {"type": "string"},
                        "alternatives": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "university",
                        "confidence",
                        "degree_level",
                        "field_indicated",
                        "reasoning",
                        "alternatives",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": "What university does this regalia come from?"},
                ],
            }
        ],
    )

    import json
    text = next(b.text for b in response.content if b.type == "text")
    return jsonify(json.loads(text))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
