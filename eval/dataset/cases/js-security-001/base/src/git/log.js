const { execFile } = require("child_process");

function recentCommits(branch, callback) {
  execFile("git", ["log", "--oneline", "-n", "20", branch], callback);
}

module.exports = { recentCommits };
