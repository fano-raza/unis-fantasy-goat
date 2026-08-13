import { redirect } from "next/navigation";

// Bare /team has no view of its own -- Profile is the specific team-profile
// sub-page, per the user's explicit request that /team itself not double as
// the profile view.
export default function TeamPage() {
  redirect("/team/profile");
}
