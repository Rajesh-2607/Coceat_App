import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Card, PageHeader } from "../lib/ui";
import type { ModuleKey } from "./modules";

/** Placeholder for modules that are configured but not built yet (billing, money and buying come next). */
export function ComingSoon({ module }: { module?: ModuleKey }) {
  const { t } = useTranslation();
  return (
    <section className="space-y-4">
      <PageHeader title={module ? t(`nav.${module}`) : t("common.notFound")} />
      <Card>
        <p className="text-lg text-slate-600">{module ? t("home.comingSoon") : t("common.notFoundHint")}</p>
        <Link to="/w" className="mt-3 inline-flex min-h-11 items-center font-medium text-violet-700">
          ← {t("nav.home")}
        </Link>
      </Card>
    </section>
  );
}
