from flask import Flask, send_from_directory

app = Flask(__name__)   # ✅ define app here

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('../Frontend', filename)

if __name__ == "__main__":
    app.run(debug=True)
