# DetectMate Service Framework

Welcome to the DetectMate Service Framework documentation. DetectMate is a flexible, component-based framework for
building distributed detection and processing services.

The Detectmate Framework consists of the [Detectmate Service](https://github.com/ait-detectmate/DetectMateService) and the [Detectmate Library](https://github.com/ait-detectmate/DetectMateLibrary). The DetectMate Service is a very generic Microservice that handles the input, forwards it to the DetectMate Library, which processes the data, and finally sends the results back to the output interfaces.

![High Level Schema]( images/High-Level-Schema.drawio.png)

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

## Contribution

We're happily taking patches and other contributions. Please see the following links for how to get started:

- [Git Workflow](contribution.md)
- [Development Details](development.md)

## License

DetectMateService is Free Open Source Software and uses the [EUPL-1.2 License](https://github.com/ait-detectmate/DetectMateService/blob/main/LICENSE.md)
