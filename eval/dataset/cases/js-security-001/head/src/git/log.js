const { exec } = require("child_process");

function recentCommits(branch, callback) {
  exec(`git log --oneline -n 20 ${branch}`, callback);
}

module.exports = { recentCommits };
