# Latent Exchange

Latent Exchange is a protocol for arranging exchanges when a direct barter is not possible.
It represents what participants can offer,
what they want, and the conditions under which they would trade. A matching
engine can then propose bilateral swaps, multilateral cycles, or bundles that
each participant may accept or reject.

The central idea is that exchange value is contextual. It depends not only on an
asset and its quantity, but also on timing, preferences, trust, delivery risk,
utility, and the alternatives available to each participant. Given the rise of AI agents,
it becomes feasible to represent such intents at scale.

## Motivation

A direct barter requires a *double coincidence of wants*: each participant must
want what the other offers, at compatible quantities and at the same time. A
network can remove some of this constraint. For example:

- Alice offers design work and needs bicycle repair.
- Ben offers bicycle repair and needs vegetables.
- Chen offers vegetables and needs design work.

No bilateral swap satisfies everyone, but the cycle Alice → Chen → Ben → Alice
can.

This protocol does not rely on the claim that barter historically preceded
money. Adam Smith used barter and exchange as part of his account of the
division of labour.[^smith] David Graeber later argued that credit and social
obligation often preceded cash exchange, while barter was more characteristic
of trade between strangers or of situations in which currency was
unavailable.[^graeber] Latent Exchange extends on the theory that David Graeber proposed.

## Model

Let `P` be the set of participants and `K` the set of asset or service types.
At decision time $t$, let $H_t$ be the versioned historical state available to
the protocol. It contains prior proposal and settlement outcomes, their context,
the parties' roles, timestamps, attestations, disputes, corrections, and the
confidence that may be placed in each fact. $H_{p q}(t)$ denotes the relevant
history between $p$ and $q$, while $H_p(t)$ may also include $p$'s broader,
context-specific record with the network.

Each participant `p` declares:

- $O_p$: offers, including quantity, quality, location, availability, and the
  participant's cost of providing them;
- $W_p$: wants and acceptable substitutes;
- $C_p$: hard constraints, such as deadlines or minimum quantities;
- $U_p(X; O_p, W_p, H_t)$: the participant's estimated utility for proposal
  `X`, conditional on relevant history; and
- $R_p(X; H_t)$: delivery, counterparty, and settlement risk inferred from the
  proposal and relevant history.

An exchange proposal is a set of directed transfers:

```math
X = \{x_{p q k}\},
```

where $x_{p q k} \ge 0$ is the quantity of item or service $k$ transferred from
participant $p$ to participant $q$. In practice, a transfer also needs terms
such as quality, location, delivery time, and settlement conditions; the
quantity-only notation keeps the model readable.

For each participant, the proposal produces an incoming and an outgoing bundle:

```math
\mathrm{in}_{p k}(X) = \sum_{q \in P} x_{q p k},
\qquad
\mathrm{out}_{p k}(X) = \sum_{q \in P} x_{p q k}.
```

The declarations factor into the proposal as follows:

- **Offers bound outgoing transfers.** If $o_{p k}$ is the available quantity of
  type $k$ in $O_p$, then
  $\mathrm{out}_{p k}(X) \le o_{p k}$. The proposed transfer must also
  match the offer's quality, timing, location, and other terms. The cost or
  inconvenience of supplying the outgoing bundle reduces $U_p$.
- **Wants evaluate incoming bundles.** $W_p$ describes desired items,
  acceptable substitutes, target quantities, and relative preferences. It
  determines how $\mathrm{in}_p(X)$ contributes to $U_p$. A want may
  therefore be soft: receiving less than the target can still have value.
- **Constraints reject invalid bundles.** $C_p$ is a predicate over the whole
  proposal, not just one item. It can require a minimum incoming quantity, cap
  an outgoing quantity, link two transfers, impose a deadline, or reject a
  counterparty. The proposal is valid for $p$ only when $C_p(X) = \mathrm{true}$.
- **History changes expected outcomes.** $H_t$ may indicate that a participant
  usually delivers a particular service late, that two participants have a
  reliable relationship, or that an outcome is disputed or weakly attested.
  This can change both the value $p$ expects to receive and the risk $p$ assigns
  to the same nominal transfer.

History should normally be a soft input to utility and risk. It becomes a hard
filter only when $C_p$ or protocol policy contains an explicit, verifiable rule,
such as requiring a minimum number of confirmed deliveries for a high-value
exchange. Filing a dispute, having little history, or receiving an unverified
claim should not silently make a participant ineligible.

A proposal is **feasible** only if every outgoing transfer is covered by an
offer and all inventory, capacity, timing, and policy constraints hold. It is
**individually rational** for participant $p$ when:

```math
\Delta U_p(X; O_p, W_p, H_t) - \lambda_p R_p(X;H_t) \ge \tau_p,
```

where $\Delta U_p(X; O_p, W_p, H_t)$ is the expected value of the incoming
bundle minus the cost of the outgoing bundle, relative to not trading;
$\lambda_p$ is the participant's sensitivity to risk; and $\tau_p$ is their
reservation threshold. Because $U_p$, $\lambda_p$, and the history visible to
$p$ may differ, two participants can rationally assign different utility to the
same counterparty and proposal.

For exchange clearing, this yields a proposal space that depends directly on
all participants' declarations:

```math
\mathcal{F}_{\mathrm{clear}}(O, W, C;H_t) =
\{
X \mid
\begin{array}{l}
\mathrm{out}_p(X) \text{ is covered by } O_p,\\
C_p(X) = \mathrm{true},\\
\Delta U_p(X; O_p, W_p,H_t) - \lambda_p R_p(X;H_t) \ge \tau_p
\end{array}
\text{ for every } p \in P
\}.
```

Candidate generation uses $O$ and $W$ to create plausible transfer edges.
History-conditioned acceptance and delivery estimates can prioritize which
edges are explored. Constraint checking then removes edges and bundles that
violate $C$. The solver assembles the remaining edges into complete proposals
and ranks them by history-conditioned utility, risk, and operational complexity.

The matching engine can search for a proposal such as:

```math
X^*_{\mathrm{clear}} =
\underset{X \in \mathcal{F}_{\mathrm{clear}}(O,W,C;H_t)}
{\mathrm{argmax}}
[
\sum_{p \in P} w_p \Delta U_p(X; O_p, W_p,H_t)
- \lambda R(X;H_t)
- \mu \kappa(X)
],
```

where $R(X;H_t)$ aggregates proposal-level settlement risk and $\kappa(X)$
penalizes operational complexity. Historical estimates should carry sample size,
recency, context, provenance, and uncertainty rather than presenting an
unqualified reputation score. The weights $w_p$ and the history model must be
chosen transparently and audited for systematic unfairness.

Feasibility and individual rationality do not imply consent: every proposal
still requires explicit approval unless the participant has granted narrowly
scoped authority to an agent.

## The latent representation

The system may learn an embedding $z_p(t)$ from a participant's current intent
and the relevant, permitted view of $H_p(t)$, together with an embedding $z_k$
for each offer or want. These representations can help retrieve compatible
candidates from a large network. A separate, calibrated model can estimate:

```math
s_{p q}(X) = \Pr(\text{participant } p \text{ accepts and } q \text{ delivers}
\mid X, H_{p q}(t), H_p(t), H_q(t)),
```

The estimate can affect candidate retrieval, $U_p$, and $R_p$, but it remains a
matching signal rather than a price, balance, or transferable currency. It must
also report uncertainty: a new participant with no history is not equivalent to
a participant with evidence of repeated failure. There is no reason for zero to
mean that a trade should occur.

Calling this representation **latent money** would combine two related but
distinct mechanisms: exchange clearing and mutual credit. Both may use the same
matching engine, but only mutual credit creates persistent obligations.

### Exchange clearing, proposals, and permission

Exchange clearing is the direct output of the matching process described above.
The engine searches $\mathcal{F}_{\mathrm{clear}}(O,W,C;H_t)$ and returns a
candidate $X^*_{\mathrm{clear}}$. This is a **proposal**, not an executed
exchange. The engine has shown that the transfers fit the submitted offers,
wants, constraints, and historical state; it has not shown that it is authorized
to act for the participants.

Let the affected participants be:

```math
P(X) = \{p \in P \mid
\exists q \in P, k \in K:\; x_{p q k} + x_{q p k} > 0
\}.
```

Each participant may sign a delegation policy $\Gamma_p$ that names an agent or
matching engine and defines exactly which proposals it may approve. A useful
delegation includes:

- permitted asset and service types, counterparties, and jurisdictions;
- maximum quantities and estimated values per exchange and per time period;
- minimum incoming bundles and permitted substitutes;
- expiry, revocation nonce, and maximum settlement delay;
- whether the delegate may only propose, may reserve inventory, or may also
  authorize settlement; and
- whether the delegate may use mutual credit and, if so, separate credit limits.

For either a clearing proposal $X$ or a credit proposal $Q$, write the proposal
generically as $Y$. Authorization for participant $p$ is:

```math
\mathrm{Authorized}_p(Y) =
\mathrm{ValidSignature}_p(c_Y)
\;\lor\;
(
\mathrm{ValidDelegation}(\Gamma_p)
\land \mathrm{ValidDelegateSignature}_{\Gamma_p}(c_Y)
\land \Gamma_p(Y) = \mathrm{true}
),
```

where $c_Y$ is the commitment to the exact proposal, including settlement terms.
The executable clearing space is:

```math
\mathcal{F}^{\mathrm{exec}}_{\mathrm{clear}}
= \{X \in \mathcal{F}_{\mathrm{clear}}
\mid \mathrm{Authorized}_p(X) \text{ for every } p \in P(X)\}.
```

If no applicable delegation exists, the proposal remains pending until every
affected participant explicitly approves it. Silence is not approval. If one
participant rejects the proposal or its approval expires, the engine must either
discard the entire atomic proposal or construct a new one and obtain fresh
authorization. A signature for one proposal must not be reusable for another;
the signed commitment should include the chain, contract, proposal nonce,
expiry, and matcher or policy version.

### Mutual-credit state

Mutual credit relaxes the requirement that everyone receive their desired value
within the same clearing cycle. A participant may receive now and compensate the
network later. This requires an explicit unit of account. That unit is not the
latent embedding or acceptance score.

Let the authoritative credit-ledger state at time $t$ be:

```math
L_t = (b(t), \ell(t), u(t), \rho(t), N_t,
\text{unit}, \text{policy version}),
```

where:

- $b_p(t)$ is participant $p$'s balance; a positive balance means the network
  owes value to $p$, while a negative balance means $p$ owes value to the
  network;
- $\ell_p(t) \ge 0$ is the maximum permitted debt, so normally
  $b_p(t) \ge -\ell_p(t)$;
- $u_p(t)$ is an optional positive-balance limit used to limit concentration;
  take $u_p(t)=+\infty$ when no such limit exists;
- $\rho_p(t) \ge 0$ is debit capacity already reserved by approved but unsettled
  proposals;
- $N_t$ is the set of consumed nullifiers or transaction identifiers; and
- the unit and policy version identify the accounting, credit-limit, default,
  fee, and settlement rules.

The matching engine must not be the sole keeper of $L_t$. An authoritative smart
contract or replicated ledger owns the state transition. The matcher reads a
particular state root, constructs a proposed transition, and supplies the data
or proof needed to validate it. This permits multiple matchers and prevents one
operator from silently changing balances or limits.

Credit limits are ledger policy, not matching output. A transparent risk or
governance process may derive $\ell_p(t)$ from collateral, completed exchanges,
guarantees, and other approved records in $H_t$, but the matcher may only consume
the resulting limit. Disputed or low-confidence outcomes should not be treated
as confirmed failures. Raising a limit requires its own authorized ledger
transition; it cannot be smuggled into the proposal that spends the new capacity.

### A mutual-credit proposal

A mutual-credit proposal must contain both real transfers and their agreed
credit accounting:

```math
Q = (X, A, T),
```

where $X$ is the transfer set; $A = \{a_{p q j}\}$ is a set of non-negative,
directed credit entries; and $T$ specifies reservation, delivery, finalization,
expiry, and rollback conditions. Each accounting leg $j \in J(Q)$ must reference
either a transfer in $X$ or an explicit policy item such as a fee or reserve
contribution. Credit amounts must come from participant-supplied terms,
negotiation, or a previously accepted policy. The matching engine cannot infer
a binding price from the latent vectors and impose it unilaterally.

For a transfer from $p$ to $q$, the provider $p$ earns credit and the receiver
$q$ incurs an equal debit. The proposed balance change is:

```math
\Delta b_p(Q) =
\sum_{q \in P, j \in J(Q)} a_{p q j}
- \sum_{q \in P, j \in J(Q)} a_{q p j}.
```

The affected set is
$P(Q)=\{p \mid p \in P(X) \text{ or } \Delta b_p(Q) \ne 0\}$. System accounts
used for fees, reserves, or loss allocation are included in this accounting set
even when they follow protocol level authorization rules rather than human
approval.

Consequently:

```math
\sum_{p \in P} \Delta b_p(Q) = 0,
\qquad
b_p(t+1) = b_p(t) + \Delta b_p(Q).
```

If balances begin with $\sum_p b_p(0)=0$, every valid transition preserves
$\sum_p b_p(t)=0$. Each unit of account requires a separate conserved ledger;
balances denominated in different units cannot be added together.

Credit is therefore formed as a matched debit-credit pair. The matcher does not
mint an unbacked positive balance. Fees, reserves, insurance pools, or write-offs
must appear as explicit system accounts so that the conservation rule remains
auditable.

Credit changes the participant's utility calculation. Let $V_p(b)$ represent
the value—or expected burden—to $p$ of holding balance $b$. A credit proposal is
individually rational only when:

```math
\Delta U_p(X; O_p, W_p,H_t)
+ V_p(b_p(t+1)) - V_p(b_p(t))
- \lambda_p R_p(Q,L_t,H_t)
\ge \tau_p.
```

The risk term now includes not only delivery risk but also the chance that
positive credit cannot later be spent, counterparties default, governance
changes the unit, or the network loses liquidity.

The feasible mutual-credit proposal space extends
$\mathcal{F}_{\mathrm{clear}}(O,W,C;H_t)$ with credit entries, ledger state, and
settlement terms:

```math
\mathcal{F}_{\mathrm{credit}}(O,W,C;L_t,H_t)
= \{
Q=(X,A,T) \mid
\begin{array}{l}
\mathrm{out}_p(X) \text{ is covered by } O_p,\\
C_p(Q)=\mathrm{true},\\
\sum_p \Delta b_p(Q)=0,\\
b_p(t)+\Delta b_p(Q)-\rho_p(t) \ge -\ell_p(t),\\
b_p(t)+\Delta b_p(Q) \le u_p(t),\\
\Delta U_p(X;O_p,W_p,H_t)+V_p(b_p(t+1))-V_p(b_p(t))\\
\qquad-\lambda_pR_p(Q,L_t,H_t) \ge \tau_p,\\
T \text{ is valid under the current ledger policy}
\end{array}
\text{ for every } p \in P(Q)
\}.
```

Here $C_p(Q)$ extends the original constraints to credit terms such as the unit,
maximum debit, minimum credit received, acceptable pricing range, repayment
expectations, and whether partial settlement is allowed. Existing reservations
$\rho_p(t)$ are deducted when checking debt capacity so that concurrent
proposals cannot promise the same credit line twice. If partial settlement is
allowed, the reservation must cover the worst negative balance reachable under
any permitted partial-settlement sequence, not merely the final net change.

Call the entire left-hand side of the individual-rationality condition
$S_p(Q;L_t,H_t)$, participant $p$'s history-conditioned, credit-adjusted
surplus. The matcher may rank feasible credit proposals with an objective such
as:

```math
Q^*_{\mathrm{credit}} =
\underset{Q \in \mathcal{F}_{\mathrm{credit}}(O,W,C;L_t,H_t)}
{\mathrm{argmax}}
[
\sum_{p \in P(Q)} w_p S_p(Q;L_t,H_t)
- \mu \kappa(Q)
- \eta G(L_{t+1})
],
```

where $\kappa(Q)$ measures operational complexity and $G(L_{t+1})$ penalizes
systemic risks such as concentrated positive claims, correlated debt, or poor
liquidity. As with clearing, this ranking chooses a proposal; it grants no
authority to execute it. The executable space remains smaller:

```math
\mathcal{F}^{\mathrm{exec}}_{\mathrm{credit}}
= \{Q \in \mathcal{F}_{\mathrm{credit}}(O,W,C;L_t,H_t)
\mid \mathrm{Authorized}_p(Q) \text{ for every } p \in P(Q)\}.
```

A delegation that permits direct clearing does not automatically permit an
agent to incur debt. Credit delegation should separately limit the most negative
resulting balance, credit amount per proposal, cumulative exposure, units,
pricing ranges, counterparties, expiry, and settlement conditions. Without that
permission, each affected participant must sign $c_Q$, a commitment to $X$,
$A$, $T$, and the referenced ledger-state root.

### How mutual credit is formed and extinguished

The full lifecycle is:

1. **Establish the unit and rules.** Governance defines the unit of account,
   eligibility, credit-limit method, fees, default allocation, disputes, exits,
   and upgrade procedure before balances are created.
2. **Commit intent.** A participant's private intent states whether credit is
   acceptable, their pricing or valuation bounds, maximum resulting debt, and
   repayment constraints. Any agent delegation is committed or registered
   separately.
3. **Read authoritative state.** The matcher selects recent finalized ledger and
   history roots and reads or proves the relevant balances, limits,
   reservations, and permitted historical predicates.
4. **Construct terms.** The matcher finds $Q=(X,A,T)$, shows each participant
   their transfers, credit amount, projected balance, risk, and settlement
   conditions, and commits to the complete proposal.
5. **Validate.** Deterministic code checks membership in
   $\mathcal{F}_{\mathrm{credit}}$. A ZK proof may show that committed private
   intents, balances, and historical records satisfy the rules without revealing
   them.
6. **Authorize and reserve.** Participants or valid delegates sign the proposal.
   The ledger records the offer reservation and atomically reserves enforceable
   on-chain assets and debit capacity against the referenced state; stale or
   conflicting proposals fail. For each participant whose proposed balance
   change is negative, the reservation increases by
   $\max(0,-\Delta b_p(Q))$. The transaction must recheck the debt limit before
   recording this reservation. A physical item's availability remains an
   off-chain claim until custody or delivery can be attested.
7. **Deliver and finalize.** Once $T$'s delivery evidence is satisfied, the
   ledger simultaneously credits providers, debits receivers, records
   nullifiers, and releases reservations. Failure or expiry follows the agreed
   rollback, partial-settlement, or dispute path rather than silently editing
   balances.
8. **Recirculate or extinguish.** A participant with a negative balance moves
   toward zero by providing value in a later proposal. A participant with a
   positive balance spends it by receiving value. Credit is extinguished as
   corresponding positive and negative balances return to zero.

For example, all balances may begin at zero. Ben repairs Alice's bicycle for 10
credits, producing $b_{\mathrm{Ben}}=+10$ and $b_{\mathrm{Alice}}=-10$. Alice
later provides six credits of design work to Chen, producing
$b_{\mathrm{Alice}}=-4$ and $b_{\mathrm{Chen}}=-6$, while Ben remains at $+10$.
If Ben then receives six credits of vegetables from Chen, Chen returns to zero
and Ben falls to $+4$. A final four-credit service from Alice to Ben returns both
remaining balances to zero. Each step is a separately authorized ledger
transition, and the balances always sum to zero.

Positive credit is a claim on the future willingness and ability of the network
to provide value, not a guaranteed external-currency deposit. Credit limits,
collateral or loss reserves, default mutualization, dormant balances, account
closure, and governance capture therefore need explicit rules. A participant
with a non-zero balance should not be able to exit by abandoning the associated
claim or obligation.

### Default, redemption, and exit

In a pure mutual-credit system, a positive balance is normally redeemed by
spending it with another participant, not by demanding external currency from a
central issuer. If the protocol promises conversion into an external asset,
that is an additional reserve-backed redemption mechanism with separate custody,
liquidity, and insolvency risks.

When a negative balance defaults, deleting only that debt would break the
zero-sum invariant and leave positive balances unsupported. A pre-agreed default
transition should therefore:

1. freeze the defaulter's unused credit line and pending proposals;
2. apply posted collateral, guarantor commitments, or a funded loss reserve;
3. allocate any remaining shortfall according to an explicit rule—for example,
   a member assessment or proportional reduction of positive claims;
4. record balanced entries between the defaulted account and the accounts that
   absorb the loss; and
5. retain evidence, appeal deadlines, and governance authorization for the
   write-off.

Voluntary exit should normally require a zero balance, no open reservations, and
no unresolved disputes. Transferring a non-zero balance to another participant
is a novation: the receiving party and the ledger policy must explicitly accept
the transferred claim or obligation.

## Proposed exchange flow

1. **Declare intent.** Participants provide structured offers, wants,
   constraints, privacy preferences, and credit terms. They separately register
   any agent delegation. Free text can supplement, but should not replace, the
   structured record that the participant reviews and signs.
2. **Retrieve candidates.** Embeddings find semantically related offers and
   acceptable substitutes. Permitted historical features estimate acceptance,
   delivery, and settlement likelihood; hard filters remove impossible matches.
3. **Construct a proposal.** The solver produces either a clearing proposal $X$
   or, only for participants who accept credit, a mutual-credit proposal
   $Q=(X,A,T)$ tied to a finalized ledger root.
4. **Validate.** Deterministic checks or a proof establish that the proposal is
   in the relevant feasible space. For credit, validation also checks balance
   conservation, credit limits, reservations, and settlement policy.
5. **Explain and authorize.** Each participant sees what they give, what they
   receive, the schedule, material risks, any credit entries, their projected
   balance, the material historical factors used, and why the proposal was
   selected. A valid delegate may approve only within its registered scope;
   otherwise the participant must explicitly sign.
6. **Reserve.** Once every affected party is authorized, the ledger atomically
   reserves enforceable assets and, when applicable, debit capacity, while
   recording reservations against off-chain offers. A failed reservation
   invalidates the proposal rather than silently changing its terms.
7. **Deliver and settle.** Escrow, deposits, staged delivery, or atomic
   settlement reduce the chance that one completed leg leaves another
   participant exposed. The ledger applies only the transition authorized in
   the committed proposal.
8. **Record outcomes.** The system records delivery quality, timeliness,
   disputes, cancellations, mutually confirmed completion, and any finalized
   balance change. Signed or attested outcome events are committed into the next
   version of $H_t$; later corrections or appeals add superseding events.

AI agents may help translate intent, discover substitutes, estimate risk, and
negotiate within explicit limits. Deterministic code should enforce inventory,
authorization, settlement, and other hard constraints.

## Trust-minimized private records and governance

Cryptography can prove that a record was committed, signed, not silently altered, and used by
an agreed computation. It cannot by itself prove that an off-chain description
of quality, delivery, or fault is true. The system therefore combines private,
tamper-evident records with attestations, counterparty confirmation, disputes,
and governance.

### Outcome records and historical state

Each proposal produces zero or more versioned outcome events. A canonical event
should contain or commit to:

- the proposal commitment and each participant's role in it
- asset or service category and the outcome context needed for future relevance
- completed, cancelled, expired, disputed, or partially completed status
- delivery timeliness and conformity to the agreed specification
- mutually confirmed facts, unilateral claims, and adjudicated findings as
  distinct fields
- signer or attester identifiers, evidence commitments, and confidence level
- event time, settlement time, dispute window, and policy version, and
- a reference to any earlier event that this event corrects or supersedes.

$H_t$ may also contain separately typed historical attestations that are not
exchange outcomes—for example, account continuity, a professional credential,
available collateral, or a capacity certification. Each needs an issuer,
subject, scope, issuance time, expiry, revocation status, and evidence
commitment. Only information relevant and permitted for the current exchange
context should enter $U_p$, $R_p$, or a constraint.

Raw evidence may remain encrypted off-chain. Let $e_j$ be the canonical encoding
of event $j$ and $c^H_j=\mathrm{Commit}(e_j;r_j)$ its commitment. The
historical state can be represented by a versioned root:

```math
\mathrm{root}_H(t) =
\mathrm{MerkleRoot}(\{c^H_j \mid e_j \text{ is recorded by }t\}).
```

Committed events should be append-only, but their interpretation need not be.
Corrections, appeals, and dispute decisions add superseding events. The active
view $H_t$ is produced by deterministic versioned rules that select the current
status without pretending that an old commitment was erased.

### How history affects matching

The matcher derives context-specific features from the permitted active view of
$H_t$. Direct history $H_{p q}(t)$ may be especially relevant, but community
history $H_p(t)$ can help when two participants have not interacted before. The
feature function and model version must be identified so that a result can be
recomputed or proven later.

History can affect a proposal in four separate places:

1. **Retrieval.** The estimated probability of acceptance and delivery helps
   decide which candidate edges are worth exploring.
2. **Utility.** $U_p(X;O_p,W_p,H_t)$ changes when expected quality, lateness,
   repeat-relationship value, or coordination cost changes.
3. **Risk.** $R_p(X;H_t)$ may combine non-delivery, quality, dispute,
   counterparty, settlement, and—for mutual credit—default and liquidity risk.
   Participant-specific $\lambda_p$ means the same evidence can affect people
   differently.
4. **Constraints.** History excludes a proposal only when an explicit
   participant or protocol rule in $C_p$ requires a verified predicate. It is
   otherwise a ranking input rather than a hidden eligibility rule.

A proposal-level model may estimate:

```math
\pi(X;H_t) = \Pr(
\text{all required approvals and deliveries complete}
\mid X,H_t
).
```

Low $\pi$ may reduce expected utility, increase risk, cause the matcher to seek
collateral or staged settlement, or lower the proposal's rank. It should not be
presented as certainty. The estimate should expose relevant evidence, sample
size, time window, uncertainty, and model version to the participants who are
asked to rely on it.

Historical use needs safeguards against feedback loops and unfair exclusion:

- distinguish absence of history from evidence of failure
- weight outcomes by recency, context similarity, attestation strength, and
  whether they remain disputed
- do not treat a complaint, cancellation, or adverse claim as fault without the
  status and evidence needed by policy
- provide correction, appeal, rehabilitation, and expiry or reduced weighting
  for old events
- penalizes Sybil resets and reputation farming without exposing unnecessary identity information
- exclude protected characteristics and unjustified proxy variables
- audit whether lower ranking creates a self-reinforcing lack of opportunity
- let participants inspect the material historical reasons for a proposal,
  rejection, deposit requirement, or credit-limit decision

### Commitments and later verification

Raw offers, wants, constraints, identities, and histories should not be written
to a public blockchain. Instead, a participant can encode an intent using a
versioned canonical schema:

```math
I_p = \mathrm{Encode}(O_p, W_p, C_p, \text{nonce}, \text{expiry},
\text{schema version})
```

and publish a randomized commitment:

```math
c_p = \mathrm{Commit}(I_p; r_p).
```

The commitment is **binding**, so the participant cannot later substitute a
different intent, and **hiding**, so an observer cannot recover the intent. A
plain hash is not necessarily hiding: offers and quantities may have too little
entropy to resist guessing. The protocol should use a reviewed commitment
scheme with fresh randomness and domain separation. Many commitments can be
batched under a Merkle root to reduce on-chain cost.

Later, the participant can either reveal $I_p$ and $r_p$ to open the commitment
or provide a zero-knowledge proof of a narrower claim—for example, that an offer
had sufficient quantity, was unexpired, or satisfied a policy—without revealing
the rest of the intent.

Historical proofs can use the same pattern. A participant might prove that the
active records under $\mathrm{root}_H(t)$ contain at least a threshold
number of confirmed, on-time outcomes in a relevant category, that no finalized
default is present in a stated time window, or that a published risk band was
computed by an agreed model. The public predicate should reveal no more than the
decision requires. The proof must bind the history root, event selection rules,
context, time window, and model version, otherwise an operator could cherrypick
favourable records or use an obsolete scoring rule.

A matching proof could expose only the public statement:

```math
\mathrm{VerifyMatch}
(\text{intent root}, \text{history root}, \text{ledger root},
\text{matcher ID}, c_Y, \text{epoch}) = \mathrm{true},
```

where $Y$ is either a clearing proposal $X$ or a credit proposal $Q$, and
$c_Y = \mathrm{Commit}(Y; r_Y)$ is its randomized commitment. A clearing
proposal uses a distinguished null ledger root. The proof uses the intents,
commitment randomness, permitted historical records, and any private ledger
openings as witness data. For a deterministic matching function $M$, it should
establish that:

- every input opens a registered, active commitment under the intent root
- every historical feature or predicate is derived from active records under
  the referenced history root using the agreed event-selection, correction, and
  dispute rules
- every outgoing transfer is covered by an offer and no reserved quantity is
  reused
- all encoded participant constraints hold
- any encoded utility, risk, or acceptance calculation used by $M$ applies the
  identified history-model version to the committed inputs
- a clearing proposal belongs to $\mathcal{F}_{\mathrm{clear}}$, or a credit
  proposal belongs to $\mathcal{F}_{\mathrm{credit}}$ under the referenced
  ledger state
- for credit, the balance changes conserve the unit, respect limits and existing
  reservations, and produce the committed next-state values
- the proposal committed by $c_Y$ is the exact output of the agreed version of
  $M$, including its tie-breaking rule, and
- nullifiers or reservation identifiers prevent the same offer from settling
  twice.

Individual rationality can be proven only to the extent that preferences and
thresholds have been encoded in the committed intent. The proof does not replace
consent. The matcher should send $Y$ and $r_Y$ to the affected participants over
an authenticated private channel. Each participant can recompute $c_Y$, inspect
the proposal, and sign that commitment before settlement.

Commitments and proofs establish consistency with committed data and code. They
do **not** establish that a physical item exists, a service was performed, or a
participant's original claim was truthful. Those facts require mutually signed
receipts, trusted or decentralized attestations, and a dispute process. An
outcome commitment can later be selectively opened to an arbitrator or used to
prove a reputation predicate without publishing the underlying evidence.

### Proving the matching function

A deliberately small and deterministic matching function is a good candidate
for [EZKL][^ezkl] as such risk models can be easily implemented in PyTorch and represented as ONNX.
It can prove that a particular model produced a claimed
output from committed inputs and supports verifier generation for EVM
applications. Such a proof demonstrates correct model execution but does not
demonstrate that the model is accurate, unbiased, robust, or trained on honest
data.

To keep proving tractable, an initial matcher should use:

- integer or fixed-point arithmetic with explicit bounds;
- a fixed maximum number of participants, items, and candidate edges per batch;
- cycles of bounded length and a deterministic tie-breaker;
- a public matcher binary or model hash, schema version, and policy version;
  and
- a small public output containing only the proposal commitment and facts
  required for settlement.

Natural language interpretation and unconstrained agent negotiation should stay
outside the proved core. An agent may translate a request into structured
fields, but the participant should inspect and sign the resulting commitment.
Before selecting a proving stack, benchmark proof time, memory use, proof size,
on-chain verification cost, recursion or aggregation, and the security maturity
of the exact versions used.

### MPC for private matching

Zero knowledge hides witness data from the verifier, but a conventional prover
still receives the private inputs. If no single matching operator should see the
combined order book, participants can secret-share their intents among an MPC
committee. The committee jointly evaluates $M$ and reveals only the permitted
output, such as a proposal to its participants or a commitment to that proposal.
The same committee can derive approved historical aggregates or risk features
without revealing the underlying outcome records to one operator.
MPC has been demonstrated for privacy-preserving inventory matching in systems
such as Prime Match.[^prime-match]

One possible composition is:

1. Each participant commits to an intent and distributes authenticated shares
   whose reconstruction is consistent with that commitment.
2. The MPC committee privately checks candidate compatibility and computes the
   deterministic matching function.
3. The committee reveals the proposal only to affected participants and posts a
   proposal commitment.
4. A publicly verifiable proof links the committed inputs, agreed matcher, and
   proposal commitment; the participants then approve settlement

MPC does not automatically produce a succinct, publicly verifiable proof, and a
zkVM does not automatically support distributed witness generation. Their
composition needs an explicit protocol rather than an assumption that the two
systems can simply be connected. The design must state its corruption threshold,
semi-honest or malicious security model, collusion assumptions, availability
requirements, and behaviour when a committee member aborts.

### On-chain and off-chain boundaries

The chain should contain only what shared verification and settlement require:

- commitment or Merkle roots and their schema versions
- intent, historical record, and attestation registry roots
- matcher, history model, credit policy, and verification key identifiers
- finalized credit ledger roots or public balances, depending on the privacy
  model
- expiries, nullifiers, inventory and debit reservations, authorization records,
  and proposal commitments
- proofs or proof verification results; and
- minimal settlement receipts and adjudicated dispute outcomes

Encrypted off-chain storage should hold raw intents, commitment openings,
private balance and credit-limit openings, identity information, detailed
outcome events, attestations, model features, messages, and dispute evidence.
Derived risk scores should be recomputable outputs tied to a model and history
root, not permanent facts copied into every record. Even hiding commitments leak
metadata such as timing, frequency, and wallet links. Batching, relayers,
short-lived exchange keys, delayed publication, and careful event design may
reduce that leakage.

A credible protocol also needs:

- explicit consent and revocable delegation
- an appeal and correction process
- versioned rules for historical inclusion, context, decay, and dispute status
- purpose-limited access to private records
- resistance to fake identities, collusion, and reputation farming
- transparent fees, ranking criteria, and governance changes
- jurisdiction-specific review before supporting regulated goods, labour,
  credit, tax reporting, or securities claims.

## Phased prototype

### Phase 1: exchange clearing

The smallest useful prototype would avoid credit and on-chain identity while
testing commitments and proofs:

1. Define canonical, versioned schemas for intents, proposals, and outcomes,
   including commitment randomness, expiry, and nullifier handling.
2. Start with divisible goods or clearly specified services in one local
   community.
3. Generate direct matches and cycles of at most three or four participants.
4. Record canonical outcome events, including confirmations, disputes, and
   corrections, and derive a versioned test history root.
5. Start with inspectable historical features such as confirmed completion
   count, category, recency, and uncertainty. Test cold-start and disputed-record
   behaviour before introducing learned utility or risk models.
6. Use a deterministic solver for feasibility and a simple, inspectable ranking
   function.
7. Commit a batch of private test intents, prove the resulting proposal locally,
   and verify it against the commitment root before attempting on-chain
   verification.
8. Require unanimous approval, then simulate reservation, settlement, failure,
   and rollback. Add MPC only after the single-prover statement is stable.
9. Measure match rate, participant surplus, completion rate, time to match,
   cancellation rate, probability calibration, cold-start access,
   distributional fairness, and explanation quality.

### Phase 2: mutual credit

Add credit only after clearing, authorization, and settlement are stable:

1. Use a closed test group, one non-convertible unit, zero initial balances, and
   manually governed fixed credit limits that the matcher cannot change.
2. Implement the ledger state machine for proposing, authorizing, reserving,
   expiring, finalizing, disputing, and releasing $Q=(X,A,T)$.
3. Add invariant and state-machine tests proving that balances sum to zero,
   debt limits include concurrent reservations, nullifiers cannot be reused,
   and unauthorized transitions fail.
4. Require explicit participant signatures for every credit proposal before
   introducing any delegated authority to incur debt.
5. Simulate partial delivery, stale state roots, matcher equivocation, committee
   aborts, default, loss allocation, and attempted exit with a non-zero balance.
6. Introduce scoped credit delegation, then test revocation and cumulative
   exposure limits under concurrent proposals.
7. Only after the plaintext reference ledger is auditable, replace balances and
   limits with commitments and prove the same transition rules in ZK. Add MPC
   when hiding the combined inputs from the prover becomes a measured need.

## Open research questions

- How should the system elicit preferences without requiring participants to
  reveal sensitive information or inviting strategic manipulation?
- How can it compare heterogeneous goods without quietly recreating a single
  market price?
- Which fairness rule should govern conflicts between total surplus, equal
  access, and the inclusion of new or low-reputation participants?
- How should context, recency, uncertainty, disputes, and rehabilitation change
  the effect of historical outcomes on $U_p$ and $R_p$?
- How can the system resist Sybil resets and reputation farming without making
  private identity or a permanent global reputation score mandatory?
- How should a multilateral exchange unwind after partial delivery?
- Which commitment scheme and canonical encoding best balance hiding,
  circuit efficiency, on-chain cost, and long-term auditability?
- Can an MPC matcher and publicly verifiable proof be composed with acceptable
  latency, cost, leakage, and resilience to aborts?
- Which real-world attestations are credible enough to update reputation while
  still permitting correction, selective disclosure, and appeals?
- Under what conditions would mutual credit add value beyond exchange clearing,
  and who would absorb default losses?

## References

[^smith]: Adam Smith, [*An Inquiry into the Nature and Causes of the Wealth of
    Nations*, Book I, Chapter II](https://en.wikisource.org/wiki/The_Wealth_of_Nations/Book_I/Chapter_2)
    (1776); see also Chapter IV.

[^graeber]: David Graeber, [*Debt: The First 5,000
    Years*](https://davidgraeber.org/books/debt-the-first-5000-years/), Chapter
    2, "The Myth of Barter" (2011). The earlier *Toward an Anthropological
    Theory of Value: The False Coin of Our Own Dreams* (2001) develops related
    arguments about value and exchange.

[^ezkl]: [EZKL documentation](https://docs.ezkl.xyz/) and [proof-verification
    lifecycle](https://docs.ezkl.xyz/getting-started/verify/).

[^ezkl-security]: [EZKL security notes](https://docs.ezkl.xyz/security/).

[^prime-match]: Antigoni Polychroniadou et al., ["Prime Match: A
    Privacy-Preserving Inventory Matching
    System"](https://www.usenix.org/conference/usenixsecurity23/presentation/polychroniadou),
    *32nd USENIX Security Symposium* (2023).

## Notation reference

The model uses the following conventions:

- Uppercase symbols generally denote sets, structured records, proposals, or
  functions; lowercase symbols generally denote individual entries or scalar
  values.
- A subscript identifies the participant or entry to which a value belongs.
  Arguments after a semicolon identify contextual state, such as history or the
  credit ledger, rather than a choice variable.
- $X$ is a clearing proposal, $Q$ is a mutual-credit proposal, and $Y$ means
  either proposal type when the same rule applies to both.
- $R$ denotes risk. Lowercase $r$ denotes fresh commitment randomness; these
  symbols are unrelated.
- Every schema, policy, feature function, and model is versioned even where the
  version is omitted from an equation for readability.

### Participants, indices, and state

| Symbol | Meaning |
| --- | --- |
| $P$ | Set of participants, including explicit protocol accounts when required for balanced accounting. |
| $p,q \in P$ | Participant indices. In a directed transfer, $p$ is normally the provider and $q$ the receiver. |
| $K$ | Set of asset or service types. |
| $k \in K$ | Asset or service-type index. |
| $j$ | Index for an outcome event or a credit-accounting leg, according to context. |
| $t$ | Decision or ledger time; $t+1$ denotes the state after a finalized transition. |
| $H_t$ | Versioned historical state permitted for a decision at time $t$. |
| $H_p(t)$ | Relevant network history for participant $p$. |
| $H_{p q}(t)$ | Relevant direct or relational history between participants $p$ and $q$. |
| $L_t$ | Authoritative mutual-credit ledger state at time $t$. |

### Intent, utility, and risk

| Symbol | Meaning |
| --- | --- |
| $O_p$ | Participant $p$'s offers, including quantities, attributes, availability, and provision costs. |
| $o_{p k}$ | Quantity of type $k$ that $p$ has available to offer. |
| $O$ | Collection of all participants' offer records. |
| $W_p$ | Participant $p$'s wants, substitutes, target quantities, and relative preferences. |
| $W$ | Collection of all participants' want records. |
| $C_p$ | Hard constraint predicate declared for participant $p$; $C_p(Y)=\mathrm{true}$ means proposal $Y$ satisfies it. |
| $C$ | Collection of all participant constraints. |
| $U_p(X;O_p,W_p,H_t)$ | Utility that $p$ assigns to the real transfers in $X$, conditional on intent and permitted history. |
| $\Delta U_p$ | Utility gain relative to not executing the proposal. |
| $R_p(X;H_t)$ | Risk that $p$ assigns to a clearing proposal, conditional on history. |
| $R_p(Q,L_t,H_t)$ | Delivery, settlement, liquidity, and credit risk that $p$ assigns to a credit proposal. |
| $R(X;H_t)$ | Proposal-level aggregate settlement risk used by the clearing objective. |
| $\lambda_p$ | Participant $p$'s sensitivity to risk. |
| $\lambda$ | System-level weight on aggregate risk in the clearing objective. |
| $\tau_p$ | Participant $p$'s minimum acceptable risk-adjusted surplus. |
| $w_p$ | Transparent welfare weight assigned to participant $p$ in an optimization objective. |
| $\kappa(Y)$ | Operational-complexity penalty for proposal $Y$. |
| $\mu$ | Weight applied to proposal complexity. |
| $\eta$ | Weight applied to systemic credit risk. |
| $G(L_{t+1})$ | Systemic-risk penalty for the proposed next credit-ledger state. |
| $\pi(X;H_t)$ | Estimated probability that all required approvals and deliveries for $X$ complete. |

### Clearing, matching, and authorization

| Symbol | Meaning |
| --- | --- |
| $X$ | Clearing proposal: a set of directed real-asset or service transfers. |
| $x_{p q k}$ | Quantity of type $k$ transferred from $p$ to $q$ in $X$. |
| $\mathrm{in}_{p k}(X)$ | Total quantity of type $k$ that $p$ receives under $X$. |
| $\mathrm{out}_{p k}(X)$ | Total quantity of type $k$ that $p$ provides under $X$. |
| $P(X)$ | Participants affected by at least one transfer in $X$. |
| $\mathcal{F}_{\mathrm{clear}}(O,W,C;H_t)$ | Feasible and individually rational clearing-proposal space. |
| $X^*_{\mathrm{clear}}$ | Highest-ranked clearing proposal under the stated objective. |
| $z_p(t)$ | Learned embedding of $p$'s current intent and permitted historical context. |
| $z_k$ | Learned embedding of an offer or want of type $k$. |
| $s_{p q}(X)$ | Estimated pairwise acceptance-and-delivery score for proposal $X$. |
| $Y$ | Generic proposal variable: either clearing proposal $X$ or credit proposal $Q$. |
| $\Gamma_p$ | Signed delegation policy defining what an agent or matcher may approve for $p$. |
| $c_Y$ | Randomized commitment to the exact generic proposal $Y$ and its settlement terms. |
| $\mathrm{Authorized}_p(Y)$ | Predicate that is true when $p$ or a valid in-scope delegate has approved $c_Y$. |
| $\mathcal{F}^{\mathrm{exec}}_{\mathrm{clear}}$ | Clearing proposals that are feasible and authorized by every affected participant. |

### Mutual credit

| Symbol | Meaning |
| --- | --- |
| $Q=(X,A,T)$ | Mutual-credit proposal containing real transfers, credit entries, and settlement terms. |
| $A$ | Set of directed credit-accounting entries in $Q$. |
| $a_{p q j}$ | Non-negative credit amount assigned from receiver $q$ to provider or system account $p$ for accounting leg $j$. |
| $J(Q)$ | Set of transfer-linked and policy-defined accounting legs in $Q$. |
| $T$ | Reservation, delivery, finalization, expiry, partial-settlement, and rollback terms. |
| $b_p(t)$ | Credit balance of $p$ at time $t$; positive means the network owes $p$, negative means $p$ owes the network. |
| $b(t)$ | Vector of all participant balances at time $t$. |
| $\Delta b_p(Q)$ | Net balance change proposed for $p$ by $Q$. |
| $\ell_p(t)$ | Maximum permitted debt magnitude for $p$. |
| $\ell(t)$ | Vector of participant debt limits. |
| $u_p(t)$ | Optional positive-balance limit for $p$. |
| $u(t)$ | Vector of positive-balance limits. |
| $\rho_p(t)$ | Debit capacity already reserved for approved but unsettled proposals involving $p$. |
| $\rho(t)$ | Vector of all debit reservations. |
| $N_t$ | Set of consumed nullifiers or transaction identifiers at time $t$. |
| $V_p(b)$ | Value or expected burden that participant $p$ assigns to holding credit balance $b$. |
| $S_p(Q;L_t,H_t)$ | History-conditioned, credit-adjusted surplus of $Q$ for participant $p$. |
| $P(Q)$ | Human and protocol accounts affected by transfers or balance changes in $Q$. |
| $\mathcal{F}_{\mathrm{credit}}(O,W,C;L_t,H_t)$ | Feasible and individually rational mutual-credit proposal space. |
| $Q^*_{\mathrm{credit}}$ | Highest-ranked mutual-credit proposal under the stated objective. |
| $c_Q$ | Commitment to $Q$, including $X$, $A$, $T$, and the referenced state root. |
| $\mathcal{F}^{\mathrm{exec}}_{\mathrm{credit}}$ | Credit proposals that are feasible and authorized by every affected participant or protocol account. |

The credit-ledger tuple is:

```math
L_t=(b(t),\ell(t),u(t),\rho(t),N_t,\text{unit},\text{policy version}).
```

It packages the credit variables with the unit of account and the rules
governing limits, defaults, fees, and settlement.

### Private records and cryptographic verification

| Symbol | Meaning |
| --- | --- |
| $I_p$ | Canonically encoded private intent of participant $p$. |
| $e_j$ | Canonically encoded historical outcome or attestation event $j$. |
| $r_p,r_j,r_Y$ | Fresh secret randomness used respectively for intent, historical-event, and proposal commitments. |
| $c_p$ | Commitment to participant $p$'s private intent $I_p$. |
| $c^H_j$ | Commitment to historical event $e_j$. |
| $\mathrm{root}_H(t)$ | Versioned Merkle root committing to recorded historical events by time $t$. |
| $\mathrm{Encode}(\cdot)$ | Canonical, versioned serialization used before committing to structured data. |
| $\mathrm{Commit}(m;r)$ | Hiding and binding commitment to message $m$ using randomness $r$. |
| $\mathrm{MerkleRoot}(\cdot)$ | Function that batches commitments into a single authenticated root. |
| $M$ | Versioned deterministic matching or validation program whose execution may be proven. |
| $\mathrm{ValidSignature}_p(c_Y)$ | Predicate verifying that participant $p$ signed proposal commitment $c_Y$. |
| $\mathrm{ValidDelegation}(\Gamma_p)$ | Predicate verifying that $p$'s delegation exists, is current, and is not revoked. |
| $\mathrm{ValidDelegateSignature}_{\Gamma_p}(c_Y)$ | Predicate verifying the named delegate's approval of $c_Y$. |
| $\mathrm{VerifyMatch}(\cdot)$ | Public verification statement linking state roots, matcher version, epoch, and proposal commitment. |
| $\text{intent root}$ | Public root committing to the active batch of private intents. |
| $\text{history root}$ | Public historical-state root; normally $\mathrm{root}_H(t)$. |
| $\text{ledger root}$ | Public commitment to $L_t$, or a distinguished null value for a clearing proposal. |
| $\text{matcher ID}$ | Hash or identifier of the exact matching or validation program and configuration. |
| $\text{epoch}$ | Bounded validity period in which the proof and referenced roots may be used. |
| $\Pr(\cdot)$ | Probability under the identified, calibrated statistical model. |
