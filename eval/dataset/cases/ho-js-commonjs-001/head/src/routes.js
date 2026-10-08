const { slugify } = require("./strings");

function articlePath(title) {
  return `/articles/${slugify(title)}`;
}

module.exports = { articlePath };
