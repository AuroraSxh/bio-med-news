import { ProductTimeline } from "@/components/product-timeline";

export default function ProductDetailPage({
  params,
}: {
  params: { slug: string };
}) {
  return <ProductTimeline slug={params.slug} />;
}
