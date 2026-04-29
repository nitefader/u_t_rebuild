# SignalPlan And Position Lifecycle

The Account owns positions.

If an Account accepts an opening SignalPlan, it must keep processing related
SignalPlans from the same Deployment for the resulting position.

## Lifecycle

```text
Deployment emits opening SignalPlan
-> Account accepts/rejects/sizes
-> Governor approves/rejects
-> OrderManager creates Account order
-> BrokerAdapter submits
-> BrokerSync reconciles fills
-> Account position opens
-> Account keeps listening for related position-management SignalPlans
-> Account reduces, closes, trails, moves stop, or holds
-> BrokerSync updates truth
-> Position remains explainable at every step
```

## Related SignalPlan Types

Related SignalPlans may include:

- full close
- partial close, such as close 50 percent
- target scale-out
- stop exit
- trailing stop update
- breakeven move
- runner management
- logical exit rule

Do not assume every close SignalPlan means flatten 100 percent.

## Lineage Requirements

Every Account order and trade must link back to:

- Account id
- Deployment id
- Strategy id
- opening SignalPlan id when applicable
- current SignalPlan id
- intent: open, close, reduce, target, stop, trail, breakeven, runner, logical_exit

## Position Explanation Context

Every Account-owned position must be explainable.

The explanation context must answer:

- why the position exists
- which SignalPlan opened it
- which Deployment and Strategy produced it
- when it opened
- how it was sized
- what Account risk rules applied
- what Governor decision approved it
- what stop, target, runner, or logical-exit plan applies
- which related SignalPlans have been received
- which orders and fills changed it
- current quantity
- current exposure
- current protective orders
- current unresolved risks
- whether sync state is fresh or stale

## AI Explain This Position

The UI may expose an `Explain this position` action.

AI receives the explanation context and may summarize, assess, and explain.

AI must not:

- approve trades
- reject trades
- resize positions
- submit orders
- cancel orders
- override Governor
- modify broker/account truth
