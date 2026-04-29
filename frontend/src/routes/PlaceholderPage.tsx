import { EmptyState } from "@/components/empty/EmptyState";
import { PageHeader } from "./PageHeader";

/**
 * Placeholder used by routes whose backend read-model has not
 * landed yet. Honest, never silent — names the missing endpoint.
 */
export function PlaceholderPage({
  title,
  subtitle,
  awaiting,
}: {
  title: string;
  subtitle?: string;
  awaiting: string;
}): JSX.Element {
  return (
    <div className="space-y-4">
      <PageHeader title={title} subtitle={subtitle} />
      <EmptyState
        title={`${title} not yet wired`}
        message={`This surface is awaiting ${awaiting}. The page will render real data the moment the backend boundary lands.`}
      />
    </div>
  );
}
