"use client";
import { Page } from "@/components/Page";
import { NotBuilt, PageHeader } from "@/components/ui";

export default function Screen() {
  return (
    <Page current="Monitoring">
      <PageHeader title="Monitoring" subtitle="Post-MVP concept, shown in the design for context only." />
      <NotBuilt what="Monitoring" phase="Post-MVP">Production monitoring is outside the MVP scope.</NotBuilt>
    </Page>
  );
}
