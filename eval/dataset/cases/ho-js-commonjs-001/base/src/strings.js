function slugify(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function titleCase(value) {
  return value.replace(/\b\w/g, (c) => c.toUpperCase());
}

module.exports = { slugify, titleCase };
