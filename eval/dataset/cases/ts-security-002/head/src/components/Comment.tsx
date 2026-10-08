type Props = { author: string; body: string };

export function Comment({ author, body }: Props) {
  return (
    <article>
      <h4>{author}</h4>
      <p dangerouslySetInnerHTML={{ __html: body }} />
    </article>
  );
}
