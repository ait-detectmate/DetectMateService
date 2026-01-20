# DetectMate Service Framework

Welcome to the DetectMate Service Framework documentation. DetectMate is a flexible, component-based framework for
building distributed detection and processing services.

It uses NNG's messaging architecture to process data in real-time.

## Key features

- **Modular design**: easily extensible with custom processors and components.
- **Resilient networking**: built on top of [`pynng`](https://pynng.readthedocs.io/en/latest/) (NNG) for high-performance messaging.
- **Configurable**: fully configurable via YAML files or environment variables.
- **Service management**: built-in CLI for starting, stopping, and monitoring the service.
- **Scalable**: run multiple independent service instances.

## Getting started

Check out the [Installation](installation.md) guide to set up the service, and then proceed to
[Configuration](configuration.md) and [Usage](usage.md) to learn how to run it.
