def extract_java_entities(tree, full_code: str = ""):
    classes = []
    functions = []
    endpoints = []

    for _, node in tree.filter(javalang.tree.ClassDeclaration):
        methods = []

        for method in node.methods:
            params = [
                Parameter(name=param.name, type=_java_type(param.type))
                for param in method.parameters
            ]

            position = getattr(method, "position", None)
            start_line = getattr(position, "line", None) if position is not None else None

            if start_line is not None:
                start_line, end_line, source = _java_source_range(full_code, start_line)
            else:
                start_line = None
                end_line = None
                source = None

            signature = (
                f"{_java_type(method.return_type)} "
                f"{method.name}("
                + ", ".join(
                    f"{param.type or 'Object'} {param.name}"
                    for param in params
                )
                + ")"
            )

            methods.append(Function(
                name=method.name,
                signature=signature,
                parameters=params,
                return_type=_java_type(method.return_type),
                source=source,
                lineno=start_line,
                end_lineno=end_line,
            ))

        bases = [node.extends.name] if node.extends else []
        classes.append(ClassInfo(
            name=node.name,
            bases=bases,
            methods=methods,
        ))

    return classes, functions, endpoints