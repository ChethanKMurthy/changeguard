function titleCase(value) {
  return value.replace(/\b\w/g, (c) => c.toUpperCase());
}

module.exports = { titleCase };
