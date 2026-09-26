/** Who is signed in. The session itself is an HttpOnly cookie the page can't
 *  read, so the gateway's /auth/me is the only way to know. */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchMe, type User } from '../api/auth';
import { claimRun } from './runStore';

export const ME_KEY = ['me'] as const;

export function useSession() {
  const me = useQuery({ queryKey: ME_KEY, queryFn: fetchMe, retry: false, staleTime: 5 * 60_000 });
  return { user: me.data ?? null, isLoading: me.isPending, error: me.error, retry: me.refetch };
}

/** Call after a successful login or email confirmation. */
export function useSignedIn() {
  const queryClient = useQueryClient();
  return (user: User) => {
    // A different account in the same tab: drop everything cached for the
    // previous one, not just the saved run.
    if (claimRun(user.id)) queryClient.clear();
    queryClient.setQueryData(ME_KEY, user);
  };
}
