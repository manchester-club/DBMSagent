opt_concurrently:
			CONCURRENTLY					{ $$ = true; }
			| /*EMPTY*/						{ $$ = false; }
		;

			/* ALTER TABLE <name> DETACH PARTITION <partition_name> [CONCURRENTLY] */
			| DETACH PARTITION qualified_name opt_concurrently
				{
					n->subtype = AT_DetachPartition;
					cmd->concurrent = $4;
				}
			/* ALTER TABLE <name> ENABLE ALWAYS */
			| ENABLE_P ALWAYS
				{
					n->subtype = AT_EnableAlways;
				}
